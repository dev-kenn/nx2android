// Android port, Vulkan backend: LSFG-style frame generation (framegen_vk.c).
// Optional post-process module, a no-op unless DM_FRAMEGEN=1. Stage 2: each present copies the game's
// composited frame into a storage image, runs a compute pass over (current, previous) frames into an
// output image and copies the output back over the frame. The pass is a test blend, not the LSFG shaders yet.
//   DM_FRAMEGEN=1          on
//   DM_FRAMEGEN_MIX=<0..1> blend weight of the current frame (default 1 = unchanged picture); lower shows the previous frame
//
// See docs/framegen-plan.md for the full design.
#pragma once

#include "gfx_vk.h"

// Read the environment (called when the swapchain is created). Resources are made on the first frame.
void framegen_init(void);

// Process one frame: src is the swapchain image in PRESENT_SRC_KHR, and is left in that layout.
// Called in vk_present() after the PRESENT_SRC barrier and before vkEndCommandBuffer. No-op when inactive.
void framegen_submit(VkCommandBuffer cb, VkImage src, VkExtent2D ext);

// Destroy all resources (called when the swapchain is destroyed).
void framegen_destroy(void);

// Frames processed this run.
uint64_t framegen_frame_count(void);
