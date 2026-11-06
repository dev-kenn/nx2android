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
    for (uint32_t i = 0; i < 32; i++) {
        if ((rq.memoryTypeBits & (1 << i)) &&
            ((V.mem_prop[i].propertyFlags & props) == props)) {
            ai.memoryTypeIndex = i; break;
        }
    }
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
    ic.usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    ic.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    ic.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    VkImage img;
    if (vkCreateImage(dev, &ic, NULL, &img) != VK_SUCCESS) return VK_NULL_HANDLE;
    VkMemoryRequirements rq; vkGetImageMemoryRequirements(dev, img, &rq);
    VkMemoryAllocateInfo ai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    ai.allocationSize = rq.size; ai.memoryTypeIndex = 0;
    for (uint32_t i = 0; i < 32; i++) {
        if ((rq.memoryTypeBits & (1u << i)) &&
            ((V.mem.propertyTypes[i].allowedProperties & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) == VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) {
            ai.memoryTypeIndex = i; break;
        }
    }
    VkDeviceMemory mem;
    if (vkAllocateMemory(dev, &ai, NULL, &mem) != VK_SUCCESS) {
        vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE;
    }
    if (vkBindImageMemory(dev, img, mem, 0) != VK_SUCCESS) {
        vkFreeMemory(dev, mem, NULL); vkDestroyImage(dev, img, NULL); return VK_NULL_HANDLE;
    }
    *out_mem = mem; return img;
}

