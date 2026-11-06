// Android port, Vulkan backend: LSFG-style frame generation (framegen_vk.c).
// Optional post-process module: reads the game's final composited frame and produces
// an intermediate frame using the user-supplied shaders from Lossless.dll.
//
// The module is a no-op when DM_FRAMEGEN=0 or when no shader pack is available.
// It follows the same pattern as the rotation pre-transform (gfx_vk_present.c g_rot.*):
//   - A flip chain of two images + descriptors for intermediate storage
//   - One compute dispatch per frame: read src, post-process to flip_chain, blit to swapchain
//
// See docs/framegen-plan.md for the full design.
#pragma once

#include "gfx_vk.h"

typedef struct {
    // Flip chain for intermediate post-processing output
    VkImage out[2];            // two output images (back / front)
    VkDeviceMemory out_mem[2];
    VkImageView out_view[2];
    
    // Descriptor set for the source texture (the game's composited frame)
    VkDescriptorSetLayout dsl;
    VkPipelineLayout layout;
    VkDescriptorPool pool;
    VkDescriptorSet set[2];    // one per flip-chain index
    
    // Pipeline and shaders
    VkSampler samp;
    VkShaderModule vs_module;
    VkShaderModule fs_module;
    VkPipeline pipe[2];        // one per flip-chain index (avoids descriptor collision)
    
    // Per-frame fence state for GPU-CPU sync (prevents collisions)
    VkFence fences[4];         // one per in-flight frame (max 4 with 3 swapchain images)
    
    // State
    int initialized;           // 1 when all resources are valid
    int active;                // DM_FRAMEGEN=1 and shader pack found
    uint32_t num_swapchain;    // number of swapchain images (for collision tracking)
    VkExtent2D ext;            // extent the flip chain images were created for
} framegen_t;

// Initialize the flip chain and pipeline (called once during vk_present_init).
void framegen_init(void);

// Process one frame: takes the game's final composited image in src, writes
// an interpolated/upscaled frame to the swapchain. Called in vk_present() between
// the PRESENT_SRC barrier and vkEndCommandBuffer when framegen is active.
// ext: the logical extent (used for work-group sizing).
void framegen_submit(VkCommandBuffer cb, VkImage src, VkExtent2D ext);

// Shutdown: destroy all resources (called during swapchain recreation).
void framegen_destroy(void);

// Debug: how many frames were processed this run.
uint64_t framegen_frame_count(void);

// Set num_swapchain for collision tracking (from gfx_vk_present.c)
void framegen_set_num_swapchain(uint32_t n);
