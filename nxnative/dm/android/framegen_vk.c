// Android port, Vulkan backend: LSFG-style frame generation (framegen_vk.c).
// Optional post-process module: reads the game's final composited frame and produces
// an intermediate frame using the user-supplied shaders from Lossless.dll.
//
// Flip chain architecture:
//   - Two flip chain images act as back/front buffers for intermediate storage
//   - One compute dispatch per frame: read src, post-process to flip_chain, blit to swapchain
//   - Fence-based sync prevents GPU-ahead-of-CPU collisions (max_in_flight <= 2)

#include "framegen_vk.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

static framegen_t g_fg = {0};
static uint64_t g_fg_count;

// ---- Helpers ----

static VkImage create_image(VkDevice dev, VkExtent2D ext, VkFormat fmt,
                            VkImageUsageFlags usage, VkMemoryPropertyFlags props) {
    VkImageCreateInfo ic = {VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    ic.imageType = VK_IMAGE_TYPE_2D;
    ic.format = fmt;
    ic.extent.width = ext.width;
    ic.extent.height = ext.height;
    ic.extent.depth = 1;
    ic.mipLevels = 1;
    ic.arrayLayers = 1;
    ic.samples = VK_SAMPLE_COUNT_1_BIT;
    ic.tiling = VK_IMAGE_TILING_OPTIMAL;
    ic.usage = usage;
    ic.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    ic.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    VkImage img;
    if (vkCreateImage(dev, &ic, NULL, &img) != VK_SUCCESS) return VK_NULL_HANDLE;
    VkMemoryRequirements rq;
    vkGetImageMemoryRequirements(dev, img, &rq);
    VkMemoryAllocateInfo ai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    ai.allocationSize = rq.size;
    ai.memoryTypeIndex = 0;
    ai.memoryTypeIndex = vk_mem_type(rq.memoryTypeBits, props, 0);
    if (ai.memoryTypeIndex == UINT32_MAX) { vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE; }
    VkDeviceMemory mem;
    if (vkAllocateMemory(dev, &ai, NULL, &mem) != VK_SUCCESS) {
        vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE;
    }
    if (vkBindImageMemory(dev, img, mem, 0) != VK_SUCCESS) {
        vkFreeMemory(dev, mem, NULL); vkDestroyImage(dev, img, NULL);
        return VK_NULL_HANDLE;
    }
    return img;
}

static VkImageView create_view(VkDevice dev, VkImage img, VkFormat fmt) {
    VkImageViewCreateInfo vi = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    vi.image = img;
    vi.viewType = VK_IMAGE_VIEW_TYPE_2D;
    vi.format = fmt;
    vi.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
    vi.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
    vi.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
    vi.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
    vi.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    vi.subresourceRange.baseMipLevel = 0;
    vi.subresourceRange.levelCount = 1;
    vi.subresourceRange.baseArrayLayer = 0;
    vi.subresourceRange.layerCount = 1;
    VkImageView view;
    return vkCreateImageView(dev, &vi, NULL, &view) == VK_SUCCESS ? view : VK_NULL_HANDLE;
}

// ---- Flip chain setup (chunk 1) ----

static bool load_lsfg_bytes(const char *path, uint8_t **out, size_t *out_len) {
    FILE *f = fopen(path, "rb"); if (!f) return false;
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    if (sz <= 0) { fclose(f); return false; }
    uint8_t *buf = malloc(sz); size_t rd = fread(buf, 1, sz, f); fclose(f);
    if (rd != (size_t)sz) { free(buf); return false; }
    *out = buf; *out_len = rd; return true;
}

static bool lsfg_pack_exists(const char *base) {
    char path[512];
    // Check multiple possible locations for the .lsfgpack bundle
    snprintf(path, sizeof path, "%s/lsfg.spv", base);
    FILE *f = fopen(path, "rb"); if (f) { fclose(f); return true; }
    snprintf(path, sizeof path, "%s/lossless_lsfg.spv", base);
    f = fopen(path, "rb"); if (f) { fclose(f); return true; }
    snprintf(path, sizeof path, "%s/framegen.spv", base);
    f = fopen(path, "rb"); if (f) { fclose(f); return true; }
    return false;
}

static uint8_t *load_lsfg_shader(const char *base, size_t *out_len) {
    char path[512];
    const char *names[] = {"lsfg.spv", "lossless_lsfg.spv", "framegen.spv", NULL};
    for (int i = 0; names[i]; i++) {
        snprintf(path, sizeof path, "%s/%s", base, names[i]);
        uint8_t *data; size_t len;
        if (load_lsfg_bytes(path, &data, &len)) return data;
    }
    return NULL;
}

// Create a storage image for the flip chain: optimal tiling, color aspect, transfer-compute usage
static VkImage create_flip_image(VkDevice dev, VkExtent2D ext, VkDeviceMemory *out_mem) {
    VkImageCreateInfo ic = {VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    ic.imageType = VK_IMAGE_TYPE_2D;
    ic.format = VK_FORMAT_R8G8B8A8_UNORM;
    ic.extent.width = ext.width; ic.extent.height = ext.height; ic.extent.depth = 1;
    ic.mipLevels = 1; ic.arrayLayers = 1;
    ic.samples = VK_SAMPLE_COUNT_1_BIT;
    ic.tiling = VK_IMAGE_TILING_OPTIMAL;
    ic.usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    ic.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    ic.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    VkImage img;
    if (vkCreateImage(dev, &ic, NULL, &img) != VK_SUCCESS) return VK_NULL_HANDLE;
    VkMemoryRequirements rq; vkGetImageMemoryRequirements(dev, img, &rq);
    VkMemoryAllocateInfo ai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    ai.allocationSize = rq.size; ai.memoryTypeIndex = 0;
    ai.memoryTypeIndex = vk_mem_type(rq.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0);
    if (ai.memoryTypeIndex == UINT32_MAX) { vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE; }
    VkDeviceMemory mem;
    if (vkAllocateMemory(dev, &ai, NULL, &mem) != VK_SUCCESS) {
        vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE;
    }
    if (vkBindImageMemory(dev, img, mem, 0) != VK_SUCCESS) {
        vkFreeMemory(dev, mem, NULL); vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE;
    }
    *out_mem = mem; return img;
}

// ---- Descriptor set layout + pipeline layout (chunk 2) ----

static void framegen_reset(framegen_t *fg) {
    for (int i = 0; i < 2; i++) {
        if (fg->out[i]) { vkDestroyImageView(V.dev, fg->out_view[i], NULL); vkDestroyImage(V.dev, fg->out[i], NULL); if (fg->out_mem[i]) vkFreeMemory(V.dev, fg->out_mem[i], NULL), fg->out_mem[i] = VK_NULL_HANDLE; fg->out[i] = VK_NULL_HANDLE; }
        fg->out_view[i] = VK_NULL_HANDLE;
    }
    fg->dsl = VK_NULL_HANDLE; fg->layout = VK_NULL_HANDLE;
    if (fg->pool) vkResetDescriptorPool(V.dev, fg->pool, 0);
    fg->samp = VK_NULL_HANDLE; fg->pipe[0] = VK_NULL_HANDLE; fg->pipe[1] = VK_NULL_HANDLE;
    fg->fences[0] = VK_NULL_HANDLE; fg->fences[1] = VK_NULL_HANDLE; fg->fences[2] = VK_NULL_HANDLE; fg->fences[3] = VK_NULL_HANDLE;
}

static bool make_layouts(framegen_t *fg) {
    // Descriptor set layout: 1 combined image sampler at binding 0
    VkDescriptorSetLayoutBinding b = (VkDescriptorSetLayoutBinding){0, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, NULL};
    VkDescriptorSetLayoutCreateInfo li = (VkDescriptorSetLayoutCreateInfo){VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, NULL, 0, 1, &b};
    return vkCreateDescriptorSetLayout(V.dev, &li, NULL, &fg->dsl) == VK_SUCCESS;
}

static bool make_pipeline_layout(framegen_t *fg) {
    VkPushConstantRange pr = (VkPushConstantRange){VK_SHADER_STAGE_FRAGMENT_BIT, 0, sizeof(float) * 4}; // ext.w, ext.h, pad, pad
    VkPipelineLayoutCreateInfo pli = (VkPipelineLayoutCreateInfo){VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, NULL, 0, 1, &fg->dsl, 1, &pr};
    return vkCreatePipelineLayout(V.dev, &pli, NULL, &fg->layout) == VK_SUCCESS;
}

static bool make_sampler(framegen_t *fg) {
    VkSamplerCreateInfo si = (VkSamplerCreateInfo){VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
    si.magFilter = VK_FILTER_LINEAR; si.minFilter = VK_FILTER_LINEAR;
    si.maxAnisotropy = 1.0f; si.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
    return vkCreateSampler(V.dev, &si, NULL, &fg->samp) == VK_SUCCESS;
}

// ---- Flip chain images + views (chunk 3) ----

static bool create_flip_chain(framegen_t *fg, VkExtent2D ext) {
    VkImageCreateInfo ic = {VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    ic.imageType = VK_IMAGE_TYPE_2D; ic.format = VK_FORMAT_R8G8B8A8_UNORM;
    ic.extent.width = ext.width; ic.extent.height = ext.height; ic.extent.depth = 1; ic.mipLevels = 1; ic.arrayLayers = 1;
    ic.samples = VK_SAMPLE_COUNT_1_BIT; ic.tiling = VK_IMAGE_TILING_OPTIMAL;
    ic.usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    ic.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ic.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    for (int i = 0; i < 2; i++) {
        if (vkCreateImage(V.dev, &ic, NULL, &fg->out[i]) != VK_SUCCESS) return false;
        VkMemoryRequirements rq; vkGetImageMemoryRequirements(V.dev, fg->out[i], &rq);
        VkMemoryAllocateInfo ai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        ai.allocationSize = rq.size; ai.memoryTypeIndex = 0;
        ai.memoryTypeIndex = vk_mem_type(rq.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0);
        if (ai.memoryTypeIndex == UINT32_MAX) return false;
        if (vkAllocateMemory(V.dev, &ai, NULL, &fg->out_mem[i]) != VK_SUCCESS) return false;
        if (vkBindImageMemory(V.dev, fg->out[i], fg->out_mem[i], 0) != VK_SUCCESS) return false;
        VkImageViewCreateInfo vi = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        vi.image = fg->out[i]; vi.viewType = VK_IMAGE_VIEW_TYPE_2D; vi.format = VK_FORMAT_R8G8B8A8_UNORM;
        vi.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT; vi.subresourceRange.levelCount = 1; vi.subresourceRange.layerCount = 1;
        if (vkCreateImageView(V.dev, &vi, NULL, &fg->out_view[i]) != VK_SUCCESS) return false;
    }
    return true;
}

// Barrier helper: layout transition for a VkImage with explicit stages/access.
// srcStage/dstStage: the pipeline stages that read/write during the old/new layouts.
// For compute reads: COMPUTE_SHADER; for transfer reads: TRANSFER; for shader writes: COMPUTE_SHADER.
static void fg_bar(VkCommandBuffer cb, VkImage img, VkImageLayout old, VkImageLayout new_,
                   VkAccessFlags srcAccess, VkAccessFlags dstAccess,
                   VkPipelineStageFlags srcStage, VkPipelineStageFlags dstStage) {
    VkImageMemoryBarrier mb = {VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    mb.oldLayout = old; mb.newLayout = new_; mb.image = img;
    mb.srcAccessMask = srcAccess; mb.dstAccessMask = dstAccess;
    mb.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT; mb.subresourceRange.baseArrayLayer = 0; mb.subresourceRange.layerCount = 1; mb.subresourceRange.baseMipLevel = 0; mb.subresourceRange.levelCount = 1;
    vkCmdPipelineBarrier(cb, srcStage, dstStage, 0, 0, NULL, 0, NULL, 1, &mb);
}

// Shader module load from loaded .spv bytes (stored in fg->shader_data/len)
static bool load_shader(VkDevice dev, const uint8_t *data, size_t len, VkShaderModule *out) {
    VkShaderModuleCreateInfo sm = {VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    sm.codeSize = len; sm.pCode = (const uint32_t *)data;
    return vkCreateShaderModule(dev, &sm, NULL, out) == VK_SUCCESS;
}

void framegen_init(void) {
    uint8_t *shader = NULL; size_t len = 0;
    shader = load_lsfg_shader("/sdcard/Android/data/", &len);
    if (!shader) return;
    free(shader);
    // TODO: pipelines, descriptor pool/sets and the flip chain are not created yet.
    // Stay inactive (no-op) until they exist; marking active now would bind null pipelines.
    g_fg.active = 0;
}

void framegen_submit(VkCommandBuffer cb, VkImage src, VkExtent2D ext) {
    if (!g_fg.active) return;  
    uint32_t ww = ext.width, wh = ext.height;
    if (g_fg.out[0] == VK_NULL_HANDLE || g_fg.ext.width != ww || g_fg.ext.height != wh) {
        for (int i = 0; i < 2; i++) {
            if (g_fg.out[i]) vkDestroyImageView(V.dev, g_fg.out_view[i], NULL),
                vkDestroyImage(V.dev, g_fg.out[i], NULL), vkFreeMemory(V.dev, g_fg.out_mem[i], NULL);
        }
        VkImageCreateInfo ic = {VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        ic.imageType = VK_IMAGE_TYPE_2D; ic.format = VK_FORMAT_R8G8B8A8_UNORM;
        ic.extent.width = ww; ic.extent.height = wh; ic.extent.depth = 1;
        ic.mipLevels = 1; ic.arrayLayers = 1; ic.samples = VK_SAMPLE_COUNT_1_BIT;
        ic.tiling = VK_IMAGE_TILING_OPTIMAL;
        ic.usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        ic.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ic.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        for (int i = 0; i < 2; i++) {
            VkDeviceMemory mem = VK_NULL_HANDLE;
            VkImage img = create_flip_image(V.dev, ext, &mem);
            if (!img) return;
            g_fg.out[i] = img; g_fg.out_mem[i] = mem;
            g_fg.out_view[i] = create_view(V.dev, img, VK_FORMAT_R8G8B8A8_UNORM);
        }
        g_fg.ext = ext;
    }  

    uint32_t idx = g_fg_count % 2;  

    // Barrier src PRESENT_SRC → TRANSFER_SRC_OPTIMAL (read source)
    fg_bar(cb, src, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
           0, VK_ACCESS_MEMORY_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);

    // Barrier flip[idx] UNDEFINED → TRANSFER_DST_OPTIMAL (write destination)
    fg_bar(cb, g_fg.out[idx], VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
           0, 0, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);

    // Copy: src → flip[idx]  
    VkImageCopy copy = {0};
    copy.srcSubresource.aspectMask = copy.dstSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    copy.extent = (VkExtent3D){(uint32_t)ww, (uint32_t)wh, 1};
    vkCmdCopyImage(cb, src, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, g_fg.out[idx],
                   VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);

    // Barrier flip TRANSFER_DST → TRANSFER_SRC (read flipped)
    fg_bar(cb, g_fg.out[idx], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
           VK_ACCESS_MEMORY_WRITE_BIT, VK_ACCESS_MEMORY_READ_BIT,
           VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);

    // Copy flip[idx] → src (dest = TRANSFER_DST)
    vkCmdCopyImage(cb, g_fg.out[idx], VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, src,
                   VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);

    // Barrier src → PRESENT_SRC_KHR for presentation  
    fg_bar(cb, src, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
           VK_ACCESS_MEMORY_WRITE_BIT, 0, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);

    g_fg_count++;
}

void framegen_destroy(void) {
    if (!g_fg.initialized) return;  
    for (int i = 0; i < 2; i++) {
        if (g_fg.out[i]) vkDestroyImageView(V.dev, g_fg.out_view[i], NULL),
            vkDestroyImage(V.dev, g_fg.out[i], NULL), vkFreeMemory(V.dev, g_fg.out_mem[i], NULL);
    }
    for (int i = 0; i < 4; i++) { if (g_fg.fences[i]) vkDestroyFence(V.dev, g_fg.fences[i], NULL); }
    if (g_fg.samp) vkDestroySampler(V.dev, g_fg.samp, NULL);
    if (g_fg.pool) vkDestroyDescriptorPool(V.dev, g_fg.pool, NULL);
    if (g_fg.dsl) vkDestroyDescriptorSetLayout(V.dev, g_fg.dsl, NULL);
    if (g_fg.layout) vkDestroyPipelineLayout(V.dev, g_fg.layout, NULL);
    for (int i = 0; i < 2; i++) { if (g_fg.pipe[i]) vkDestroyPipeline(V.dev, g_fg.pipe[i], NULL); }
    g_fg.active = 0; g_fg.initialized = 0;
}

uint64_t framegen_frame_count(void) { return g_fg_count; }  

void framegen_set_num_swapchain(uint32_t n) {
    if (n > 1) g_fg.num_swapchain = n; else g_fg.num_swapchain = 2;
}
