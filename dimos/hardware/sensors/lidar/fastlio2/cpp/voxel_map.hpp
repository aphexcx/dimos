// Copyright 2026 Dimensional Inc.
// SPDX-License-Identifier: Apache-2.0
//
// Efficient global voxel map using a hash map.
// Pure data structure: O(1) insert/update, distance-based pruning,
// and cloud export.  Integration strategies live in strategies/.

#ifndef VOXEL_MAP_HPP_
#define VOXEL_MAP_HPP_

#include <cmath>
#include <cstdint>
#include <unordered_map>

#include <pcl/point_cloud.h>
#include <pcl/point_types.h>

struct VoxelKey {
    int32_t x, y, z;
    bool operator==(const VoxelKey& o) const { return x == o.x && y == o.y && z == o.z; }
};

struct VoxelKeyHash {
    size_t operator()(const VoxelKey& k) const {
        // Fast spatial hash — large primes reduce collisions for grid coords
        size_t h = static_cast<size_t>(k.x) * 73856093u;
        h ^= static_cast<size_t>(k.y) * 19349669u;
        h ^= static_cast<size_t>(k.z) * 83492791u;
        return h;
    }
};

struct Voxel {
    float x, y, z;       // running centroid
    float intensity;
    uint32_t count;       // points merged into this voxel
};

using VoxelHashMap = std::unordered_map<VoxelKey, Voxel, VoxelKeyHash>;

class VoxelMap {
public:
    explicit VoxelMap(float voxel_size, float max_range = 100.0f)
        : voxel_size_(voxel_size), max_range_(max_range) {
        map_.reserve(500000);
    }

    /// Insert a point cloud into the map, merging into existing voxels.
    template <typename PointT>
    void insert(const typename pcl::PointCloud<PointT>::Ptr& cloud) {
        if (!cloud) return;
        float inv = 1.0f / voxel_size_;
        for (const auto& pt : cloud->points) {
            VoxelKey key{
                static_cast<int32_t>(std::floor(pt.x * inv)),
                static_cast<int32_t>(std::floor(pt.y * inv)),
                static_cast<int32_t>(std::floor(pt.z * inv))};

            auto it = map_.find(key);
            if (it != map_.end()) {
                // Running average update
                auto& v = it->second;
                float n = static_cast<float>(v.count);
                float n1 = n + 1.0f;
                v.x = (v.x * n + pt.x) / n1;
                v.y = (v.y * n + pt.y) / n1;
                v.z = (v.z * n + pt.z) / n1;
                v.intensity = (v.intensity * n + pt.intensity) / n1;
                v.count++;
            } else {
                map_.emplace(key, Voxel{pt.x, pt.y, pt.z, pt.intensity, 1});
            }
        }
    }

    /// Remove voxels farther than max_range from the given position.
    void prune(float px, float py, float pz) {
        float r2 = max_range_ * max_range_;
        for (auto it = map_.begin(); it != map_.end();) {
            float dx = it->second.x - px;
            float dy = it->second.y - py;
            float dz = it->second.z - pz;
            if (dx * dx + dy * dy + dz * dz > r2)
                it = map_.erase(it);
            else
                ++it;
        }
    }

    /// Export all voxel centroids as a point cloud.
    template <typename PointT>
    typename pcl::PointCloud<PointT>::Ptr to_cloud() const {
        typename pcl::PointCloud<PointT>::Ptr cloud(
            new pcl::PointCloud<PointT>(map_.size(), 1));
        size_t i = 0;
        for (const auto& [key, v] : map_) {
            auto& pt = cloud->points[i++];
            pt.x = v.x;
            pt.y = v.y;
            pt.z = v.z;
            pt.intensity = v.intensity;
        }
        return cloud;
    }

    size_t size() const { return map_.size(); }
    void clear() { map_.clear(); }
    void set_max_range(float r) { max_range_ = r; }
    float voxel_size() const { return voxel_size_; }
    float max_range() const { return max_range_; }

    /// Direct access to underlying map (for strategies).
    VoxelHashMap& data() { return map_; }
    const VoxelHashMap& data() const { return map_; }

private:
    VoxelHashMap map_;
    float voxel_size_;
    float max_range_;
};

#endif
