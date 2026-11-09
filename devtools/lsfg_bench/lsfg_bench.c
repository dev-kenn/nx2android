// lsfg_bench: measures the GPU time of compute shaders (SPIR-V) with dummy, zero-filled resources.
// Standalone arm64 Android command-line program; no window, own Vulkan instance/device/compute queue.
// The SPIR-V is reflected in C (descriptor sets/bindings, local size, push-constant size): no manifest needed.
//   lsfg_bench <spv dir> [--size WxH] [--runs N] [--warmup N] [--only substr] [--limit N] [--top N]
// Numbers are approximate: see README.md.

#include <vulkan/vulkan.h>
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define MAXB 64
#define MAXSETS 8

typedef struct {
    uint32_t set, binding, count;
    VkDescriptorType type;
    uint32_t dim, arrayed, fmt, skind;   // images: SPIR-V Dim, Arrayed, ImageFormat, sampled type (0 float, 1 int, 2 uint)
    uint64_t size;                        // buffers: bytes
} Bind;

typedef struct {
    uint32_t lx, ly, lz;
    uint32_t pc_size;
    int nb;
    Bind b[MAXB];
} Refl;

typedef struct {
    char name[96];
    Refl r;
    int ok;
    double ms;
} Result;

// ---------------------------------------------------------------- SPIR-V reflection
static uint32_t *g_w; static size_t g_n;         // module words
static uint32_t **g_inst; static uint32_t g_bound;
static uint32_t *g_dset, *g_dbind, *g_dblock, *g_darrstride;
static int g_rt;                                  // a runtime array was met in the last size computation
static uint64_t g_w_px, g_h_px;

#define OP(p) ((p)[0] & 0xffff)
#define WC(p) ((p)[0] >> 16)

static uint32_t constval(uint32_t id) {
    uint32_t *p = id < g_bound ? g_inst[id] : NULL;
    if (p && (OP(p) == 43 || OP(p) == 50)) return p[3];
    return 1;
}

static uint64_t type_size(uint32_t t, uint32_t mstride);

static uint64_t struct_size(uint32_t s) {
    uint32_t *sp = g_inst[s];
    uint32_t nm = WC(sp) - 2;
    uint64_t best = 0;
    for (uint32_t m = 0; m < nm; m++) {
        uint32_t off = 0, ms = 0;
        for (size_t i = 5; i < g_n;) {
            uint32_t *p = g_w + i;
            if (OP(p) == 72 && p[1] == s && p[2] == m) {
                if (p[3] == 35) off = p[4];
                else if (p[3] == 7) ms = p[4];
            }
            if (WC(p) == 0) return best;
            i += WC(p);
        }
        uint64_t e = off + type_size(sp[2 + m], ms);
        if (e > best) best = e;
    }
    return best;
}

static uint64_t type_size(uint32_t t, uint32_t mstride) {
    uint32_t *p = t < g_bound ? g_inst[t] : NULL;
    if (!p) return 0;
    switch (OP(p)) {
    case 20: return 4;
    case 21: case 22: return p[2] / 8;
    case 23: return type_size(p[2], 0) * p[3];
    case 24: {
        uint64_t col = type_size(p[2], 0);
        if (!mstride) mstride = (uint32_t)((col + 15) & ~15u);
        return (uint64_t)mstride * p[3];
    }
    case 28: {
        uint64_t el = type_size(p[2], 0);
        uint32_t st = g_darrstride[t] ? g_darrstride[t] : (uint32_t)el;
        return (uint64_t)st * constval(p[3]);
    }
    case 29: g_rt = 1; return g_darrstride[t] ? g_darrstride[t] : 4;
    case 30: return struct_size(t);
    default: return 0;
    }
}

static int reflect_spv(const uint32_t *words, size_t n, Refl *r) {
    memset(r, 0, sizeof *r);
    r->lx = r->ly = r->lz = 1;
    if (n < 5 || words[0] != 0x07230203u) return -1;
    g_w = (uint32_t *)words; g_n = n; g_bound = words[3];
    g_inst = calloc(g_bound + 1, sizeof(uint32_t *));
    g_dset = calloc(g_bound + 1, 4); g_dbind = calloc(g_bound + 1, 4);
    g_dblock = calloc(g_bound + 1, 4); g_darrstride = calloc(g_bound + 1, 4);
    for (uint32_t i = 0; i <= g_bound; i++) g_dset[i] = g_dbind[i] = 0xffffffffu;
    for (size_t i = 5; i < n;) {
        uint32_t *p = g_w + i;
        uint32_t wc = WC(p), op = OP(p);
        if (wc == 0 || i + wc > n) break;
        // result id position
        uint32_t rid = 0;
        switch (op) {
        case 19: case 20: case 21: case 22: case 23: case 24: case 25: case 26: case 27: case 28: case 29: case 30: case 32:
            rid = p[1]; break;
        case 43: case 50: case 59: rid = p[2]; break;
        default: break;
        }
        if (rid && rid < g_bound) g_inst[rid] = p;
        if (op == 71 && p[1] < g_bound) {
            if (p[2] == 34) g_dset[p[1]] = p[3];
            else if (p[2] == 33) g_dbind[p[1]] = p[3];
            else if (p[2] == 2 || p[2] == 3) g_dblock[p[1]] = p[2];
            else if (p[2] == 6) g_darrstride[p[1]] = p[3];
        } else if (op == 16 && p[2] == 17) {            // OpExecutionMode LocalSize
            r->lx = p[3]; r->ly = p[4]; r->lz = p[5];
        }
        i += wc;
    }
    for (uint32_t id = 1; id < g_bound; id++) {
        uint32_t *v = g_inst[id];
        if (!v || OP(v) != 59) continue;
        uint32_t sc = v[3];
        uint32_t *pt = g_inst[v[1]];
        if (!pt || OP(pt) != 32) continue;
        uint32_t tid = pt[3];
        uint32_t count = 1;
        for (;;) {
            uint32_t *t = g_inst[tid];
            if (t && OP(t) == 28) { count *= constval(t[3]); tid = t[2]; }
            else if (t && OP(t) == 29) { tid = t[2]; }
            else break;
        }
        uint32_t *t = g_inst[tid];
        if (!t) continue;
        if (sc == 9) { g_rt = 0; uint64_t s = type_size(tid, 0); if (s > r->pc_size) r->pc_size = (uint32_t)s; continue; }
        if (sc != 0 && sc != 2 && sc != 12) continue;
        if (g_dset[id] == 0xffffffffu || g_dbind[id] == 0xffffffffu) continue;
        if (r->nb >= MAXB) continue;
        Bind *b = &r->b[r->nb];
        memset(b, 0, sizeof *b);
        b->set = g_dset[id]; b->binding = g_dbind[id]; b->count = count > 64 ? 64 : count;
        switch (OP(t)) {
        case 25: {
            b->dim = t[3]; b->arrayed = t[5];
            uint32_t *st = g_inst[t[2]];
            b->skind = (st && OP(st) == 21) ? (st[3] ? 1 : 2) : 0;
            b->fmt = t[8];
            b->type = t[7] == 2 ? VK_DESCRIPTOR_TYPE_STORAGE_IMAGE : VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;
            if (b->dim == 5) b->type = t[7] == 2 ? VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER : VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER;
            break;
        }
        case 26: b->type = VK_DESCRIPTOR_TYPE_SAMPLER; break;
        case 27: {
            uint32_t *it = g_inst[t[2]];
            b->type = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
            if (it && OP(it) == 25) {
                b->dim = it[3]; b->arrayed = it[5];
                uint32_t *st = g_inst[it[2]];
                b->skind = (st && OP(st) == 21) ? (st[3] ? 1 : 2) : 0;
            }
            break;
        }
        case 30: {
            g_rt = 0;
            uint64_t s = struct_size(tid);
            if (g_rt) s += g_w_px * g_h_px * 4;       // runtime array: guess one dword per pixel
            if (s < 64) s = 64;
            b->size = (s + 15) & ~15ull;
            b->type = (sc == 12 || g_dblock[tid] == 3) ? VK_DESCRIPTOR_TYPE_STORAGE_BUFFER : VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
            break;
        }
        default: continue;
        }
        r->nb++;
    }
    free(g_inst); free(g_dset); free(g_dbind); free(g_dblock); free(g_darrstride);
    return 0;
}

// ---------------------------------------------------------------- Vulkan helpers
static VkInstance inst;
static VkPhysicalDevice phys;
static VkDevice dev;
static VkQueue queue;
static uint32_t qfam;
static VkPhysicalDeviceMemoryProperties memprops;
static VkPhysicalDeviceLimits limits;
static double ts_period;
static uint64_t ts_mask;
static VkCommandPool cpool;
static VkSampler g_sampler;

#define VK(x) do { VkResult _r = (x); if (_r != VK_SUCCESS) { fprintf(stderr, "vk error %d at %s:%d (%s)\n", (int)_r, __FILE__, __LINE__, #x); return -1; } } while (0)

static VkFormat fmt_from_spirv(uint32_t f, uint32_t skind) {
    static const VkFormat tab[40] = {
        VK_FORMAT_UNDEFINED, VK_FORMAT_R32G32B32A32_SFLOAT, VK_FORMAT_R16G16B16A16_SFLOAT, VK_FORMAT_R32_SFLOAT,
        VK_FORMAT_R8G8B8A8_UNORM, VK_FORMAT_R8G8B8A8_SNORM, VK_FORMAT_R32G32_SFLOAT, VK_FORMAT_R16G16_SFLOAT,
        VK_FORMAT_B10G11R11_UFLOAT_PACK32, VK_FORMAT_R16_SFLOAT, VK_FORMAT_R16G16B16A16_UNORM,
        VK_FORMAT_A2B10G10R10_UNORM_PACK32, VK_FORMAT_R16G16_UNORM, VK_FORMAT_R8G8_UNORM, VK_FORMAT_R16_UNORM,
        VK_FORMAT_R8_UNORM, VK_FORMAT_R16G16B16A16_SNORM, VK_FORMAT_R16G16_SNORM, VK_FORMAT_R8G8_SNORM,
        VK_FORMAT_R16_SNORM, VK_FORMAT_R8_SNORM, VK_FORMAT_R32G32B32A32_SINT, VK_FORMAT_R16G16B16A16_SINT,
        VK_FORMAT_R8G8B8A8_SINT, VK_FORMAT_R32_SINT, VK_FORMAT_R32G32_SINT, VK_FORMAT_R16G16_SINT,
        VK_FORMAT_R8G8_SINT, VK_FORMAT_R16_SINT, VK_FORMAT_R8_SINT, VK_FORMAT_R32G32B32A32_UINT,
        VK_FORMAT_R16G16B16A16_UINT, VK_FORMAT_R8G8B8A8_UINT, VK_FORMAT_R32_UINT,
        VK_FORMAT_A2B10G10R10_UINT_PACK32, VK_FORMAT_R32G32_UINT, VK_FORMAT_R16G16_UINT, VK_FORMAT_R8G8_UINT,
        VK_FORMAT_R16_UINT, VK_FORMAT_R8_UINT };
    if (f > 0 && f < 40) return tab[f];
    if (skind == 1) return VK_FORMAT_R32_SINT;
    if (skind == 2) return VK_FORMAT_R32_UINT;
    return f == 0 ? VK_FORMAT_R8G8B8A8_UNORM : VK_FORMAT_R16G16B16A16_SFLOAT;
}

static int find_mem(uint32_t bits, VkMemoryPropertyFlags want) {
    for (uint32_t i = 0; i < memprops.memoryTypeCount; i++)
        if ((bits & (1u << i)) && (memprops.memoryTypes[i].propertyFlags & want) == want) return (int)i;
    return -1;
}

// per-shader resources
typedef struct {
    VkImage img; VkImageView view; VkDeviceMemory mem;
    VkBuffer buf; VkBufferView bview;
} Res;

static int make_image(const Bind *b, Res *res, uint32_t W, uint32_t H) {
    int storage = b->type == VK_DESCRIPTOR_TYPE_STORAGE_IMAGE;
    VkFormat f = storage ? fmt_from_spirv(b->fmt, b->skind)
                         : (b->skind == 1 ? VK_FORMAT_R32_SINT : b->skind == 2 ? VK_FORMAT_R32_UINT : VK_FORMAT_R16G16B16A16_SFLOAT);
    VkImageType it = b->dim == 0 ? VK_IMAGE_TYPE_1D : b->dim == 2 ? VK_IMAGE_TYPE_3D : VK_IMAGE_TYPE_2D;
    VkExtent3D ext = { W, it == VK_IMAGE_TYPE_1D ? 1 : H, 1 };
    if (it == VK_IMAGE_TYPE_3D) { ext.width = 64; ext.height = 64; ext.depth = 64; }
    uint32_t layers = b->arrayed ? 4 : 1;
    if (b->dim == 3) layers = 6;                                    // Cube
    VkImageCreateInfo ci = { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
    ci.flags = b->dim == 3 ? VK_IMAGE_CREATE_CUBE_COMPATIBLE_BIT : 0;
    ci.imageType = it; ci.format = f; ci.extent = ext; ci.mipLevels = 1; ci.arrayLayers = layers;
    ci.samples = VK_SAMPLE_COUNT_1_BIT; ci.tiling = VK_IMAGE_TILING_OPTIMAL;
    ci.usage = (storage ? VK_IMAGE_USAGE_STORAGE_BIT : VK_IMAGE_USAGE_SAMPLED_BIT) | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    ci.sharingMode = VK_SHARING_MODE_EXCLUSIVE; ci.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    VK(vkCreateImage(dev, &ci, NULL, &res->img));
    VkMemoryRequirements mr; vkGetImageMemoryRequirements(dev, res->img, &mr);
    int mt = find_mem(mr.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (mt < 0) mt = find_mem(mr.memoryTypeBits, 0);
    VkMemoryAllocateInfo ai = { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, NULL, mr.size, (uint32_t)mt };
    VK(vkAllocateMemory(dev, &ai, NULL, &res->mem));
    VK(vkBindImageMemory(dev, res->img, res->mem, 0));
    VkImageViewCreateInfo vi = { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO };
    vi.image = res->img; vi.format = f;
    vi.viewType = b->dim == 3 ? (b->arrayed ? VK_IMAGE_VIEW_TYPE_CUBE_ARRAY : VK_IMAGE_VIEW_TYPE_CUBE)
                : it == VK_IMAGE_TYPE_1D ? (b->arrayed ? VK_IMAGE_VIEW_TYPE_1D_ARRAY : VK_IMAGE_VIEW_TYPE_1D)
                : it == VK_IMAGE_TYPE_3D ? VK_IMAGE_VIEW_TYPE_3D
                : (b->arrayed ? VK_IMAGE_VIEW_TYPE_2D_ARRAY : VK_IMAGE_VIEW_TYPE_2D);
    vi.subresourceRange = (VkImageSubresourceRange){ VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, layers };
    VK(vkCreateImageView(dev, &vi, NULL, &res->view));
    return 0;
}

static int make_buffer(const Bind *b, Res *res) {
    VkBufferUsageFlags u = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    uint64_t size = b->size;
    switch (b->type) {
    case VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER: u |= VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT; break;
    case VK_DESCRIPTOR_TYPE_STORAGE_BUFFER: u |= VK_BUFFER_USAGE_STORAGE_BUFFER_BIT; break;
    case VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER: u |= VK_BUFFER_USAGE_STORAGE_TEXEL_BUFFER_BIT; size = 4ull * 1024 * 1024; break;
    default: u |= VK_BUFFER_USAGE_UNIFORM_TEXEL_BUFFER_BIT; size = 4ull * 1024 * 1024; break;
    }
    VkBufferCreateInfo ci = { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO };
    ci.size = size; ci.usage = u; ci.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    VK(vkCreateBuffer(dev, &ci, NULL, &res->buf));
    VkMemoryRequirements mr; vkGetBufferMemoryRequirements(dev, res->buf, &mr);
    int mt = find_mem(mr.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (mt < 0) mt = find_mem(mr.memoryTypeBits, 0);
    VkMemoryAllocateInfo ai = { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, NULL, mr.size, (uint32_t)mt };
    VK(vkAllocateMemory(dev, &ai, NULL, &res->mem));
    VK(vkBindBufferMemory(dev, res->buf, res->mem, 0));
    if (b->type == VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER || b->type == VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER) {
        VkBufferViewCreateInfo vi = { VK_STRUCTURE_TYPE_BUFFER_VIEW_CREATE_INFO };
        vi.buffer = res->buf; vi.format = fmt_from_spirv(b->fmt, b->skind); vi.range = VK_WHOLE_SIZE;
        VK(vkCreateBufferView(dev, &vi, NULL, &res->bview));
    }
    return 0;
}

static int submit_wait(VkCommandBuffer cb) {
    VkSubmitInfo si = { VK_STRUCTURE_TYPE_SUBMIT_INFO };
    si.commandBufferCount = 1; si.pCommandBuffers = &cb;
    VK(vkQueueSubmit(queue, 1, &si, VK_NULL_HANDLE));
    VK(vkQueueWaitIdle(queue));
    return 0;
}

// Creates pipeline + resources for one shader, times it. Returns 0 on success.
static int bench_one(const uint32_t *code, size_t bytes, Refl *r, uint32_t W, uint32_t H, int warmup, int runs, double *out_ms) {
    int rc = -1;
    VkShaderModule sm = VK_NULL_HANDLE;
    VkDescriptorSetLayout dsl[MAXSETS] = {0};
    VkPipelineLayout pl = VK_NULL_HANDLE;
    VkPipeline pipe = VK_NULL_HANDLE;
    VkDescriptorPool pool = VK_NULL_HANDLE;
    VkDescriptorSet sets[MAXSETS] = {0};
    VkQueryPool qp = VK_NULL_HANDLE;
    VkCommandBuffer cbs[2] = {0};
    Res res[MAXB]; memset(res, 0, sizeof res);
    int nsets = 0;
    for (int i = 0; i < r->nb; i++) {
        if (r->b[i].set >= MAXSETS) { fprintf(stderr, "  set %u too high\n", r->b[i].set); goto done; }
        if ((int)r->b[i].set + 1 > nsets) nsets = r->b[i].set + 1;
    }

    VkShaderModuleCreateInfo smi = { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, NULL, 0, bytes, code };
    if (vkCreateShaderModule(dev, &smi, NULL, &sm) != VK_SUCCESS) { fprintf(stderr, "  vkCreateShaderModule failed\n"); goto done; }

    VkDescriptorSetLayoutBinding lb[MAXSETS][MAXB];
    uint32_t nlb[MAXSETS] = {0};
    for (int i = 0; i < r->nb; i++) {
        Bind *b = &r->b[i];
        VkDescriptorSetLayoutBinding *x = &lb[b->set][nlb[b->set]++];
        *x = (VkDescriptorSetLayoutBinding){ b->binding, b->type, b->count, VK_SHADER_STAGE_COMPUTE_BIT, NULL };
    }
    for (int s = 0; s < nsets; s++) {
        VkDescriptorSetLayoutCreateInfo di = { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, NULL, 0, nlb[s], lb[s] };
        if (vkCreateDescriptorSetLayout(dev, &di, NULL, &dsl[s]) != VK_SUCCESS) { fprintf(stderr, "  descriptor set layout failed\n"); goto done; }
    }
    uint32_t pcs = r->pc_size > limits.maxPushConstantsSize ? limits.maxPushConstantsSize : r->pc_size;
    VkPushConstantRange pcr = { VK_SHADER_STAGE_COMPUTE_BIT, 0, pcs };
    VkPipelineLayoutCreateInfo pli = { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, NULL, 0, (uint32_t)nsets, dsl, pcs ? 1u : 0u, &pcr };
    if (vkCreatePipelineLayout(dev, &pli, NULL, &pl) != VK_SUCCESS) { fprintf(stderr, "  pipeline layout failed\n"); goto done; }
    VkComputePipelineCreateInfo cpi = { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cpi.stage = (VkPipelineShaderStageCreateInfo){ VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, NULL, 0, VK_SHADER_STAGE_COMPUTE_BIT, sm, "main", NULL };
    cpi.layout = pl;
    if (vkCreateComputePipelines(dev, VK_NULL_HANDLE, 1, &cpi, NULL, &pipe) != VK_SUCCESS) { fprintf(stderr, "  vkCreateComputePipelines failed\n"); goto done; }

    // resources + descriptors
    uint32_t cnt[11] = {0};
    for (int i = 0; i < r->nb; i++) cnt[r->b[i].type] += r->b[i].count;
    VkDescriptorPoolSize ps[11]; uint32_t nps = 0;
    for (uint32_t t = 0; t < 11; t++) if (cnt[t]) ps[nps++] = (VkDescriptorPoolSize){ (VkDescriptorType)t, cnt[t] };
    VkDescriptorPoolCreateInfo dpi = { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO, NULL, 0, (uint32_t)(nsets ? nsets : 1), nps, ps };
    if (vkCreateDescriptorPool(dev, &dpi, NULL, &pool) != VK_SUCCESS) { fprintf(stderr, "  descriptor pool failed\n"); goto done; }
    if (nsets) {
        VkDescriptorSetAllocateInfo dai = { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO, NULL, pool, (uint32_t)nsets, dsl };
        if (vkAllocateDescriptorSets(dev, &dai, sets) != VK_SUCCESS) { fprintf(stderr, "  descriptor set alloc failed\n"); goto done; }
    }
    VkCommandBufferAllocateInfo cai = { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, NULL, cpool, VK_COMMAND_BUFFER_LEVEL_PRIMARY, 2 };
    if (vkAllocateCommandBuffers(dev, &cai, cbs) != VK_SUCCESS) goto done;

    VkCommandBufferBeginInfo bi = { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
    vkBeginCommandBuffer(cbs[0], &bi);
    VkDescriptorImageInfo dii[MAXB][64]; VkDescriptorBufferInfo dbi[MAXB][64]; VkBufferView dbv[MAXB][64];
    VkWriteDescriptorSet wr[MAXB]; memset(wr, 0, sizeof wr);
    for (int i = 0; i < r->nb; i++) {
        Bind *b = &r->b[i];
        VkWriteDescriptorSet *w = &wr[i];
        w->sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        w->dstSet = sets[b->set]; w->dstBinding = b->binding; w->descriptorCount = b->count; w->descriptorType = b->type;
        switch (b->type) {
        case VK_DESCRIPTOR_TYPE_SAMPLER:
            for (uint32_t k = 0; k < b->count; k++) dii[i][k] = (VkDescriptorImageInfo){ g_sampler, VK_NULL_HANDLE, VK_IMAGE_LAYOUT_UNDEFINED };
            w->pImageInfo = dii[i]; break;
        case VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE: case VK_DESCRIPTOR_TYPE_STORAGE_IMAGE: case VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER: {
            Bind tmp = *b;
            if (b->type == VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER) tmp.type = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;
            if (make_image(&tmp, &res[i], W, H)) goto done;
            VkImageMemoryBarrier br = { VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER };
            br.srcAccessMask = 0; br.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            br.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED; br.newLayout = VK_IMAGE_LAYOUT_GENERAL;
            br.srcQueueFamilyIndex = br.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
            br.image = res[i].img; br.subresourceRange = (VkImageSubresourceRange){ VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, VK_REMAINING_ARRAY_LAYERS };
            vkCmdPipelineBarrier(cbs[0], VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &br);
            VkClearColorValue zero; memset(&zero, 0, sizeof zero);
            vkCmdClearColorImage(cbs[0], res[i].img, VK_IMAGE_LAYOUT_GENERAL, &zero, 1, &br.subresourceRange);
            for (uint32_t k = 0; k < b->count; k++)
                dii[i][k] = (VkDescriptorImageInfo){ g_sampler, res[i].view, VK_IMAGE_LAYOUT_GENERAL };
            w->pImageInfo = dii[i]; break;
        }
        case VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER: case VK_DESCRIPTOR_TYPE_STORAGE_BUFFER:
            if (make_buffer(b, &res[i])) goto done;
            vkCmdFillBuffer(cbs[0], res[i].buf, 0, VK_WHOLE_SIZE, 0);
            for (uint32_t k = 0; k < b->count; k++) dbi[i][k] = (VkDescriptorBufferInfo){ res[i].buf, 0, VK_WHOLE_SIZE };
            w->pBufferInfo = dbi[i]; break;
        default:
            if (make_buffer(b, &res[i])) goto done;
            vkCmdFillBuffer(cbs[0], res[i].buf, 0, VK_WHOLE_SIZE, 0);
            for (uint32_t k = 0; k < b->count; k++) dbv[i][k] = res[i].bview;
            w->pTexelBufferView = dbv[i]; break;
        }
    }
    VkMemoryBarrier mb = { VK_STRUCTURE_TYPE_MEMORY_BARRIER, NULL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT };
    vkCmdPipelineBarrier(cbs[0], VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1, &mb, 0, NULL, 0, NULL);
    vkEndCommandBuffer(cbs[0]);
    if (r->nb) vkUpdateDescriptorSets(dev, (uint32_t)r->nb, wr, 0, NULL);
    if (submit_wait(cbs[0])) goto done;

    VkQueryPoolCreateInfo qi = { VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO, NULL, 0, VK_QUERY_TYPE_TIMESTAMP, 2, 0 };
    if (vkCreateQueryPool(dev, &qi, NULL, &qp) != VK_SUCCESS) goto done;
    uint32_t gx = (W + r->lx - 1) / r->lx, gy = (H + r->ly - 1) / r->ly;
    static const uint8_t zeros[256];
    vkBeginCommandBuffer(cbs[1], &bi);
    vkCmdResetQueryPool(cbs[1], qp, 0, 2);
    vkCmdBindPipeline(cbs[1], VK_PIPELINE_BIND_POINT_COMPUTE, pipe);
    if (nsets) vkCmdBindDescriptorSets(cbs[1], VK_PIPELINE_BIND_POINT_COMPUTE, pl, 0, (uint32_t)nsets, sets, 0, NULL);
    if (pcs) vkCmdPushConstants(cbs[1], pl, VK_SHADER_STAGE_COMPUTE_BIT, 0, pcs > 256 ? 256 : pcs, zeros);
    vkCmdWriteTimestamp(cbs[1], VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, qp, 0);
    vkCmdDispatch(cbs[1], gx, gy, 1);
    vkCmdWriteTimestamp(cbs[1], VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, qp, 1);
    vkEndCommandBuffer(cbs[1]);

    double sum = 0;
    for (int i = 0; i < warmup + runs; i++) {
        if (submit_wait(cbs[1])) goto done;
        uint64_t t[2];
        if (vkGetQueryPoolResults(dev, qp, 0, 2, sizeof t, t, 8, VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WAIT_BIT) != VK_SUCCESS) goto done;
        if (i >= warmup) sum += (double)((t[1] - t[0]) & ts_mask) * ts_period / 1e6;
    }
    *out_ms = runs > 0 ? sum / runs : 0;
    rc = 0;
done:
    if (queue) vkQueueWaitIdle(queue);
    if (qp) vkDestroyQueryPool(dev, qp, NULL);
    if (cbs[0]) vkFreeCommandBuffers(dev, cpool, 2, cbs);
    for (int i = 0; i < r->nb; i++) {
        if (res[i].bview) vkDestroyBufferView(dev, res[i].bview, NULL);
        if (res[i].view) vkDestroyImageView(dev, res[i].view, NULL);
        if (res[i].img) vkDestroyImage(dev, res[i].img, NULL);
        if (res[i].buf) vkDestroyBuffer(dev, res[i].buf, NULL);
        if (res[i].mem) vkFreeMemory(dev, res[i].mem, NULL);
    }
    if (pool) vkDestroyDescriptorPool(dev, pool, NULL);
    if (pipe) vkDestroyPipeline(dev, pipe, NULL);
    if (pl) vkDestroyPipelineLayout(dev, pl, NULL);
    for (int s = 0; s < nsets; s++) if (dsl[s]) vkDestroyDescriptorSetLayout(dev, dsl[s], NULL);
    if (sm) vkDestroyShaderModule(dev, sm, NULL);
    return rc;
}

static int init_vulkan(void) {
    VkApplicationInfo app = { VK_STRUCTURE_TYPE_APPLICATION_INFO, NULL, "lsfg_bench", 1, "none", 0, VK_API_VERSION_1_1 };
    VkInstanceCreateInfo ici = { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, NULL, 0, &app };
    VK(vkCreateInstance(&ici, NULL, &inst));
    uint32_t n = 0;
    VK(vkEnumeratePhysicalDevices(inst, &n, NULL));
    if (!n) { fprintf(stderr, "no Vulkan device\n"); return -1; }
    VkPhysicalDevice pd[8]; if (n > 8) n = 8;
    VK(vkEnumeratePhysicalDevices(inst, &n, pd));
    phys = pd[0];

    VkPhysicalDeviceSubgroupProperties sgp = { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES };
    VkPhysicalDeviceProperties2 p2 = { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &sgp };
    vkGetPhysicalDeviceProperties2(phys, &p2);
    VkPhysicalDeviceProperties *p = &p2.properties;
    limits = p->limits;
    ts_period = p->limits.timestampPeriod;
    printf("Device:         %s\n", p->deviceName);
    printf("Vendor/Device:  0x%04x / 0x%04x\n", p->vendorID, p->deviceID);
    printf("Driver version: 0x%08x (%u.%u.%u)\n", p->driverVersion, p->driverVersion >> 22, (p->driverVersion >> 12) & 0x3ff, p->driverVersion & 0xfff);
    printf("Vulkan API:     %u.%u.%u\n", VK_VERSION_MAJOR(p->apiVersion), VK_VERSION_MINOR(p->apiVersion), VK_VERSION_PATCH(p->apiVersion));
    printf("Subgroup size:  %u (ops mask 0x%x)\n", sgp.subgroupSize, sgp.supportedOperations);
    printf("Timestamp:      period %.3f ns\n", ts_period);
    printf("Max WG size:    %u x %u x %u (invocations %u), shared mem %u\n", limits.maxComputeWorkGroupSize[0],
           limits.maxComputeWorkGroupSize[1], limits.maxComputeWorkGroupSize[2], limits.maxComputeWorkGroupInvocations,
           limits.maxComputeSharedMemorySize);
    vkGetPhysicalDeviceMemoryProperties(phys, &memprops);

    uint32_t nq = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(phys, &nq, NULL);
    VkQueueFamilyProperties qf[16]; if (nq > 16) nq = 16;
    vkGetPhysicalDeviceQueueFamilyProperties(phys, &nq, qf);
    int found = -1;
    for (uint32_t i = 0; i < nq; i++)
        if ((qf[i].queueFlags & VK_QUEUE_COMPUTE_BIT) && qf[i].timestampValidBits) { found = (int)i; if (!(qf[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) break; }
    if (found < 0) { fprintf(stderr, "no compute queue with timestamps\n"); return -1; }
    qfam = (uint32_t)found;
    ts_mask = qf[qfam].timestampValidBits >= 64 ? ~0ull : ((1ull << qf[qfam].timestampValidBits) - 1);

    // enable every feature the device offers (shaders may need int8/16, float16, storage-without-format, ...)
    VkPhysicalDeviceVulkan12Features f12 = { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES };
    VkPhysicalDeviceVulkan11Features f11 = { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES };
    VkPhysicalDeviceFeatures2 f2 = { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2 };
    int v12 = p->apiVersion >= VK_API_VERSION_1_2;
    if (v12) { f11.pNext = &f12; f2.pNext = &f11; }
    vkGetPhysicalDeviceFeatures2(phys, &f2);
    float prio = 1.0f;
    VkDeviceQueueCreateInfo qci = { VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, NULL, 0, qfam, 1, &prio };
    VkDeviceCreateInfo dci = { VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, &f2, 0, 1, &qci };
    VK(vkCreateDevice(phys, &dci, NULL, &dev));
    vkGetDeviceQueue(dev, qfam, 0, &queue);
    VkCommandPoolCreateInfo cpi = { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, NULL, VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, qfam };
    VK(vkCreateCommandPool(dev, &cpi, NULL, &cpool));
    VkSamplerCreateInfo si = { VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO };
    si.magFilter = si.minFilter = VK_FILTER_LINEAR;
    si.addressModeU = si.addressModeV = si.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    VK(vkCreateSampler(dev, &si, NULL, &g_sampler));
    return 0;
}

static int cmp_ms(const void *a, const void *b) {
    const Result *x = a, *y = b;
    return x->ms < y->ms ? 1 : x->ms > y->ms ? -1 : 0;
}

static int cmp_name(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

int main(int argc, char **argv) {
    const char *dir = NULL, *only = NULL;
    uint32_t W = 1920, H = 1080;
    int runs = 20, warmup = 3, limit = 0, top = 10;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--size") && i + 1 < argc) { if (sscanf(argv[++i], "%ux%u", &W, &H) != 2) { fprintf(stderr, "bad --size\n"); return 2; } }
        else if (!strcmp(argv[i], "--runs") && i + 1 < argc) runs = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--warmup") && i + 1 < argc) warmup = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--only") && i + 1 < argc) only = argv[++i];
        else if (!strcmp(argv[i], "--limit") && i + 1 < argc) limit = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--top") && i + 1 < argc) top = atoi(argv[++i]);
        else if (argv[i][0] != '-') dir = argv[i];
        else { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
    }
    if (!dir) { fprintf(stderr, "usage: lsfg_bench <spv dir> [--size WxH] [--runs N] [--warmup N] [--only substr] [--limit N] [--top N]\n"); return 2; }
    if (runs < 1) runs = 1;
    g_w_px = W; g_h_px = H;

    char **names = NULL; int nn = 0, cap = 0;
    DIR *d = opendir(dir);
    if (!d) { perror(dir); return 1; }
    struct dirent *e;
    while ((e = readdir(d))) {
        size_t l = strlen(e->d_name);
        if (l < 5 || strcmp(e->d_name + l - 4, ".spv")) continue;
        if (only && !strstr(e->d_name, only)) continue;
        if (nn == cap) { cap = cap ? cap * 2 : 256; names = realloc(names, cap * sizeof *names); }
        names[nn++] = strdup(e->d_name);
    }
    closedir(d);
    qsort(names, nn, sizeof *names, cmp_name);
    if (limit > 0 && nn > limit) nn = limit;
    if (!nn) { fprintf(stderr, "no .spv files in %s\n", dir); return 1; }

    if (init_vulkan()) return 1;
    printf("Frame size:     %ux%u, %d shaders, %d warm-up + %d timed runs each\n\n", W, H, nn, warmup, runs);

    Result *res = calloc(nn, sizeof *res);
    int nfail = 0;
    for (int i = 0; i < nn; i++) {
        Result *R = &res[i];
        snprintf(R->name, sizeof R->name, "%s", names[i]);
        char path[1024]; snprintf(path, sizeof path, "%s/%s", dir, names[i]);
        FILE *f = fopen(path, "rb");
        if (!f) { fprintf(stderr, "%s: cannot open\n", path); nfail++; continue; }
        fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
        uint32_t *code = malloc((size_t)sz + 4);
        if (fread(code, 1, (size_t)sz, f) != (size_t)sz) { fclose(f); free(code); nfail++; continue; }
        fclose(f);
        if (reflect_spv(code, (size_t)sz / 4, &R->r)) { fprintf(stderr, "%s: not SPIR-V\n", names[i]); free(code); nfail++; continue; }
        fprintf(stderr, "[%d/%d] %s local %ux%ux%u, %d bindings, pc %u\n", i + 1, nn, names[i], R->r.lx, R->r.ly, R->r.lz, R->r.nb, R->r.pc_size);
        if (bench_one(code, (size_t)sz, &R->r, W, H, warmup, runs, &R->ms) == 0) R->ok = 1;
        else { fprintf(stderr, "  FAILED: %s\n", names[i]); nfail++; }
        free(code);
    }

    printf("%-28s %-10s %5s %4s %10s\n", "shader", "local", "binds", "pc", "ms");
    double total = 0; int nok = 0;
    for (int i = 0; i < nn; i++) {
        Result *R = &res[i];
        char loc[32]; snprintf(loc, sizeof loc, "%ux%ux%u", R->r.lx, R->r.ly, R->r.lz);
        if (R->ok) { printf("%-28s %-10s %5d %4u %10.4f\n", R->name, loc, R->r.nb, R->r.pc_size, R->ms); total += R->ms; nok++; }
        else printf("%-28s %-10s %5d %4u %10s\n", R->name, loc, R->r.nb, R->r.pc_size, "FAILED");
    }
    printf("\nOK %d, failed %d. Total if every OK shader runs once: %.3f ms\n", nok, nfail, total);
    qsort(res, nn, sizeof *res, cmp_ms);
    printf("\nTop %d most expensive:\n", top);
    for (int i = 0; i < top && i < nn && res[i].ok; i++)
        printf("  %2d. %-28s %ux%ux%u  %8.4f ms\n", i + 1, res[i].name, res[i].r.lx, res[i].r.ly, res[i].r.lz, res[i].ms);
    printf("\nNote: dummy zero-filled data and guessed resource sizes/formats make these numbers approximate.\n");
    return nfail ? 3 : 0;
}
