// Android port, Vulkan backend: LSFG-style frame generation (framegen_vk.c), stage 2.
// Per present: src (swapchain image) -> cur; compute(cur, prev) -> out; out -> src; cur -> prev.
// cur, prev and out are storage images that stay in GENERAL between frames. The compute shader is a test
// blend (shaders/framegen_blend.comp) standing in for the Lossless.dll shaders.

#include "framegen_vk.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "framegen_blend_comp.spv.h"

enum { IMG_CUR, IMG_PREV, IMG_OUT, NIMG };
#define FG_FMT VK_FORMAT_R8G8B8A8_UNORM

static struct {
    int active;            // DM_FRAMEGEN=1
    int failed;            // resource creation failed: stay off until the swapchain is recreated
    float mix;             // DM_FRAMEGEN_MIX
    int have_prev;         // prev holds a real frame
    VkExtent2D ext;        // extent the images were made for
    VkImage img[NIMG];
    VkDeviceMemory mem[NIMG];
    VkImageView view[NIMG];
    VkDescriptorSetLayout dsl;
    VkPipelineLayout layout;
    VkPipeline pipe;
    VkDescriptorPool pool;
    VkDescriptorSet set;
} g_fg;
static uint64_t g_fg_count;

static void fg_free_images(void) {
    for (int i = 0; i < NIMG; i++) {
        if (g_fg.view[i]) vkDestroyImageView(V.dev, g_fg.view[i], NULL);
        if (g_fg.img[i]) vkDestroyImage(V.dev, g_fg.img[i], NULL);
        if (g_fg.mem[i]) vkFreeMemory(V.dev, g_fg.mem[i], NULL);
        g_fg.view[i] = VK_NULL_HANDLE; g_fg.img[i] = VK_NULL_HANDLE; g_fg.mem[i] = VK_NULL_HANDLE;
    }
    g_fg.have_prev = 0;
}

static void fg_free_all(void) {
    if (!V.dev) return;
    vkDeviceWaitIdle(V.dev);
    fg_free_images();
    if (g_fg.pool) vkDestroyDescriptorPool(V.dev, g_fg.pool, NULL);
    if (g_fg.pipe) vkDestroyPipeline(V.dev, g_fg.pipe, NULL);
    if (g_fg.layout) vkDestroyPipelineLayout(V.dev, g_fg.layout, NULL);
    if (g_fg.dsl) vkDestroyDescriptorSetLayout(V.dev, g_fg.dsl, NULL);
    g_fg.pool = VK_NULL_HANDLE; g_fg.pipe = VK_NULL_HANDLE; g_fg.layout = VK_NULL_HANDLE; g_fg.dsl = VK_NULL_HANDLE;
    g_fg.set = VK_NULL_HANDLE; g_fg.ext = (VkExtent2D){0, 0};
}

// Pipeline, layouts and descriptor set: made once (the set's three bindings are rewritten when the images change).
static int fg_make_pipeline(void) {
    VkDescriptorSetLayoutBinding b[NIMG];
    for (int i = 0; i < NIMG; i++) b[i] = (VkDescriptorSetLayoutBinding){i, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, NULL};
    VkDescriptorSetLayoutCreateInfo li = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    li.bindingCount = NIMG; li.pBindings = b;
    if (vkCreateDescriptorSetLayout(V.dev, &li, NULL, &g_fg.dsl) != VK_SUCCESS) return 0;
    VkPushConstantRange pr = {VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(float)};
    VkPipelineLayoutCreateInfo pl = {VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pl.setLayoutCount = 1; pl.pSetLayouts = &g_fg.dsl; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &pr;
    if (vkCreatePipelineLayout(V.dev, &pl, NULL, &g_fg.layout) != VK_SUCCESS) return 0;
    VkShaderModuleCreateInfo sm = {VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    sm.codeSize = sizeof framegen_blend_comp_spv; sm.pCode = framegen_blend_comp_spv;
    VkShaderModule mod;
    if (vkCreateShaderModule(V.dev, &sm, NULL, &mod) != VK_SUCCESS) return 0;
    VkComputePipelineCreateInfo ci = {VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    ci.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    ci.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT; ci.stage.module = mod; ci.stage.pName = "main";
    ci.layout = g_fg.layout;
    VkResult r = vkCreateComputePipelines(V.dev, VK_NULL_HANDLE, 1, &ci, NULL, &g_fg.pipe);
    vkDestroyShaderModule(V.dev, mod, NULL);
    if (r != VK_SUCCESS) return 0;
    VkDescriptorPoolSize ps = {VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, NIMG};
    VkDescriptorPoolCreateInfo pc = {VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    pc.maxSets = 1; pc.poolSizeCount = 1; pc.pPoolSizes = &ps;
    if (vkCreateDescriptorPool(V.dev, &pc, NULL, &g_fg.pool) != VK_SUCCESS) return 0;
    VkDescriptorSetAllocateInfo ai = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    ai.descriptorPool = g_fg.pool; ai.descriptorSetCount = 1; ai.pSetLayouts = &g_fg.dsl;
    return vkAllocateDescriptorSets(V.dev, &ai, &g_fg.set) == VK_SUCCESS;
}

static int fg_make_images(VkExtent2D ext) {
    for (int i = 0; i < NIMG; i++) {
        VkImageCreateInfo ic = {VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        ic.imageType = VK_IMAGE_TYPE_2D; ic.format = FG_FMT;
        ic.extent = (VkExtent3D){ext.width, ext.height, 1}; ic.mipLevels = 1; ic.arrayLayers = 1;
        ic.samples = VK_SAMPLE_COUNT_1_BIT; ic.tiling = VK_IMAGE_TILING_OPTIMAL;
        ic.usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        ic.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ic.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        if (vkCreateImage(V.dev, &ic, NULL, &g_fg.img[i]) != VK_SUCCESS) return 0;
        VkMemoryRequirements rq; vkGetImageMemoryRequirements(V.dev, g_fg.img[i], &rq);
        VkMemoryAllocateInfo ai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        ai.allocationSize = rq.size;
        ai.memoryTypeIndex = vk_mem_type(rq.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0);
        if (ai.memoryTypeIndex == UINT32_MAX) return 0;
        if (vkAllocateMemory(V.dev, &ai, NULL, &g_fg.mem[i]) != VK_SUCCESS) return 0;
        if (vkBindImageMemory(V.dev, g_fg.img[i], g_fg.mem[i], 0) != VK_SUCCESS) return 0;
        VkImageViewCreateInfo vi = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        vi.image = g_fg.img[i]; vi.viewType = VK_IMAGE_VIEW_TYPE_2D; vi.format = FG_FMT;
        vi.subresourceRange = (VkImageSubresourceRange){VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        if (vkCreateImageView(V.dev, &vi, NULL, &g_fg.view[i]) != VK_SUCCESS) return 0;
    }
    VkDescriptorImageInfo di[NIMG]; VkWriteDescriptorSet w[NIMG];
    for (int i = 0; i < NIMG; i++) {
        di[i] = (VkDescriptorImageInfo){VK_NULL_HANDLE, g_fg.view[i], VK_IMAGE_LAYOUT_GENERAL};
        w[i] = (VkWriteDescriptorSet){VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
        w[i].dstSet = g_fg.set; w[i].dstBinding = i; w[i].descriptorCount = 1;
        w[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; w[i].pImageInfo = &di[i];
    }
    vkUpdateDescriptorSets(V.dev, NIMG, w, 0, NULL);
    return 1;
}

static void fg_bar(VkCommandBuffer cb, VkImage img, VkImageLayout from, VkImageLayout to,
                   VkAccessFlags sa, VkAccessFlags da, VkPipelineStageFlags ss, VkPipelineStageFlags ds) {
    VkImageMemoryBarrier mb = {VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    mb.srcAccessMask = sa; mb.dstAccessMask = da; mb.oldLayout = from; mb.newLayout = to;
    mb.srcQueueFamilyIndex = mb.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED; mb.image = img;
    mb.subresourceRange = (VkImageSubresourceRange){VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    vkCmdPipelineBarrier(cb, ss, ds, 0, 0, NULL, 0, NULL, 1, &mb);
}

void framegen_init(void) {
    const char *e = getenv("DM_FRAMEGEN"), *m = getenv("DM_FRAMEGEN_MIX");
    g_fg.active = e && atoi(e);
    g_fg.failed = 0;
    g_fg.mix = m ? (float)atof(m) : 1.0f;
    if (g_fg.mix < 0) g_fg.mix = 0;
    if (g_fg.mix > 1) g_fg.mix = 1;
    VKLOG("framegen: stage 2 compute blend %s (mix %.2f)", g_fg.active ? "on" : "off", g_fg.mix);
}

void framegen_submit(VkCommandBuffer cb, VkImage src, VkExtent2D ext) {
    if (!g_fg.active || g_fg.failed || !ext.width || !ext.height) return;
    if (!g_fg.pipe && !fg_make_pipeline()) { VKLOG("framegen: pipeline creation failed, off"); fg_free_all(); g_fg.failed = 1; return; }
    if (g_fg.ext.width != ext.width || g_fg.ext.height != ext.height) {
        vkDeviceWaitIdle(V.dev);
        fg_free_images();
        if (!fg_make_images(ext)) { VKLOG("framegen: image creation failed, off"); fg_free_images(); g_fg.failed = 1; return; }
        g_fg.ext = ext;
    }
    VkImage cur = g_fg.img[IMG_CUR], prev = g_fg.img[IMG_PREV], out = g_fg.img[IMG_OUT];
    const VkPipelineStageFlags T = VK_PIPELINE_STAGE_TRANSFER_BIT, C = VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, A = VK_PIPELINE_STAGE_ALL_COMMANDS_BIT;
    const VkImageLayout GEN = VK_IMAGE_LAYOUT_GENERAL, TS = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, TD = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, UN = VK_IMAGE_LAYOUT_UNDEFINED;
    const VkImageCopy cp = {{VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, {0, 0, 0}, {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, {0, 0, 0}, {ext.width, ext.height, 1}};
    int first = !g_fg.have_prev;

    // src -> cur
    fg_bar(cb, src, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, TS, VK_ACCESS_MEMORY_READ_BIT, VK_ACCESS_TRANSFER_READ_BIT, A, T);
    fg_bar(cb, cur, UN, TD, 0, VK_ACCESS_TRANSFER_WRITE_BIT, A, T);
    vkCmdCopyImage(cb, src, TS, cur, TD, 1, &cp);

    // compute: (cur, prev) -> out. prev and out are in GENERAL after the first frame; the first frame moves them out of UNDEFINED.
    fg_bar(cb, cur, TD, GEN, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT, T, C);
    fg_bar(cb, prev, first ? UN : GEN, GEN, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT, A, C);
    fg_bar(cb, out, UN, GEN, 0, VK_ACCESS_SHADER_WRITE_BIT, A, C);
    float t = first ? 1.0f : g_fg.mix;   // no previous frame yet: pass the current one through
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, g_fg.pipe);
    vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, g_fg.layout, 0, 1, &g_fg.set, 0, NULL);
    vkCmdPushConstants(cb, g_fg.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof t, &t);
    vkCmdDispatch(cb, (ext.width + 7) / 8, (ext.height + 7) / 8, 1);

    // out -> src, and cur -> prev for the next frame
    fg_bar(cb, out, GEN, TS, VK_ACCESS_SHADER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT, C, T);
    fg_bar(cb, src, TS, TD, VK_ACCESS_TRANSFER_READ_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, T, T);
    vkCmdCopyImage(cb, out, TS, src, TD, 1, &cp);
    fg_bar(cb, cur, GEN, TS, VK_ACCESS_SHADER_READ_BIT, VK_ACCESS_TRANSFER_READ_BIT, C, T);
    fg_bar(cb, prev, GEN, TD, VK_ACCESS_SHADER_READ_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, C, T);
    vkCmdCopyImage(cb, cur, TS, prev, TD, 1, &cp);
    fg_bar(cb, prev, TD, GEN, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT, T, C);   // the next frame's compute reads it
    fg_bar(cb, src, TD, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_MEMORY_READ_BIT, T, A);

    g_fg.have_prev = 1;
    g_fg_count++;
}

void framegen_destroy(void) { fg_free_all(); g_fg.active = 0; }

uint64_t framegen_frame_count(void) { return g_fg_count; }
