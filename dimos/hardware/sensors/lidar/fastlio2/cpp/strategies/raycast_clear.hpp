// Copyright 2026 Dimensional Inc.
// SPDX-License-Identifier: Apache-2.0
//
// Raycast clearing strategy for global voxel map integration.
// For each point in the incoming cloud, casts an inflated ray from the
// sensor origin.  Voxels along the ray (free space) are erased; voxels
// at the endpoint (surfaces) are preserved.  Ray inflation handles
// LiDAR sparsity by clearing a cylinder of voxels around each ray.

#ifndef STRATEGIES_RAYCAST_CLEAR_HPP_
#define STRATEGIES_RAYCAST_CLEAR_HPP_

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <unordered_set>

#include <pcl/point_cloud.h>

#include "voxel_map.hpp"

struct RaycastClearConfig {
    float inflate_radius = 0.0f;  // inflation radius in world units (0 = single voxel ray)
    float end_margin = -1.0f;     // stop erasing this far before hit; -1 = use voxel_size
    float min_range = 0.5f;       // skip near-sensor region where rays overlap heavily
};

/// Cast inflated rays from sensor origin through each point, erase free
/// space voxels, then insert the new cloud.
template <typename PointT>
void raycast_clear_and_insert(VoxelMap& map,
                              const typename pcl::PointCloud<PointT>::Ptr& cloud,
                              float ox, float oy, float oz,
                              const RaycastClearConfig& cfg = {}) {
    if (!cloud || cloud->empty()) {
        map.insert<PointT>(cloud);
        return;
    }

    float vs = map.voxel_size();
    float inv = 1.0f / vs;
    float end_margin = cfg.end_margin >= 0 ? cfg.end_margin : vs;
    int inflate_v = static_cast<int>(std::ceil(cfg.inflate_radius * inv));
    float step = vs;  // step at voxel-size intervals

    // Collect hit voxel keys — these are surfaces, never erase them.
    // Dilate by 1 voxel to protect neighboring surface voxels that this
    // scan didn't hit (prevents wall erosion at grazing angles).
    std::unordered_set<VoxelKey, VoxelKeyHash> hit_keys;
    hit_keys.reserve(cloud->size() * 27);  // worst case with dilation
    for (const auto& pt : cloud->points) {
        int32_t bx = static_cast<int32_t>(std::floor(pt.x * inv));
        int32_t by = static_cast<int32_t>(std::floor(pt.y * inv));
        int32_t bz = static_cast<int32_t>(std::floor(pt.z * inv));
        for (int32_t dx = -1; dx <= 1; ++dx)
            for (int32_t dy = -1; dy <= 1; ++dy)
                for (int32_t dz = -1; dz <= 1; ++dz)
                    hit_keys.insert({bx + dx, by + dy, bz + dz});
    }

    // Deduplicate rays: one ray per unique hit voxel to avoid redundant work.
    // Pick the actual point closest to each voxel center as ray endpoint.
    struct RayEnd { float x, y, z; };
    std::unordered_map<VoxelKey, RayEnd, VoxelKeyHash> unique_rays;
    unique_rays.reserve(hit_keys.size());
    for (const auto& pt : cloud->points) {
        VoxelKey k{
            static_cast<int32_t>(std::floor(pt.x * inv)),
            static_cast<int32_t>(std::floor(pt.y * inv)),
            static_cast<int32_t>(std::floor(pt.z * inv))};
        // Just keep first point per voxel (fast, good enough)
        unique_rays.emplace(k, RayEnd{pt.x, pt.y, pt.z});
    }

    // Walk rays and directly erase free-space voxels from the map.
    // Instead of building a massive free_keys set (~400k entries) and then
    // checking the map, we probe the map directly at each ray step.
    // With ~20k map voxels vs ~400k ray positions, most probes are fast
    // hash misses — no intermediate allocation needed.
    size_t cleared = 0;
    auto& m = map.data();

    for (const auto& [vk, end] : unique_rays) {
        float dx = end.x - ox, dy = end.y - oy, dz = end.z - oz;
        float len = std::sqrt(dx * dx + dy * dy + dz * dz);
        if (len < cfg.min_range) continue;

        float inv_len = 1.0f / len;
        float ux = dx * inv_len, uy = dy * inv_len, uz = dz * inv_len;
        float max_t = len - end_margin;

        // Taper zone: inflation shrinks to 0 over the last inflate_radius
        // of the ray to avoid clipping walls at grazing angles
        float taper_start = max_t - cfg.inflate_radius;

        for (float t = cfg.min_range; t < max_t; t += step) {
            float rx = ox + ux * t;
            float ry = oy + uy * t;
            float rz = oz + uz * t;

            int32_t cx = static_cast<int32_t>(std::floor(rx * inv));
            int32_t cy = static_cast<int32_t>(std::floor(ry * inv));
            int32_t cz = static_cast<int32_t>(std::floor(rz * inv));

            // Compute effective inflation: full before taper, linearly → 0
            int cur_inflate = inflate_v;
            if (inflate_v > 0 && t > taper_start) {
                float frac = (max_t - t) / cfg.inflate_radius;
                cur_inflate = static_cast<int>(std::round(inflate_v * frac));
            }

            // Directly probe & erase from map instead of collecting keys
            auto try_erase = [&](int32_t kx, int32_t ky, int32_t kz) {
                VoxelKey k{kx, ky, kz};
                if (hit_keys.count(k) == 0) {
                    auto it = m.find(k);
                    if (it != m.end()) {
                        m.erase(it);
                        ++cleared;
                    }
                }
            };

            if (cur_inflate == 0) {
                try_erase(cx, cy, cz);
            } else {
                for (int32_t ix = -cur_inflate; ix <= cur_inflate; ++ix)
                    for (int32_t iy = -cur_inflate; iy <= cur_inflate; ++iy)
                        for (int32_t iz = -cur_inflate; iz <= cur_inflate; ++iz)
                            try_erase(cx + ix, cy + iy, cz + iz);
            }
        }
    }

    if (cleared > 0) {
        printf("[raycast] %zu rays, cleared %zu voxels (inflate=%d), map %zu\n",
               unique_rays.size(), cleared, inflate_v, map.size());
    }

    map.insert<PointT>(cloud);
}

#endif
