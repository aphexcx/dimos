// Copyright 2026 Dimensional Inc.
// SPDX-License-Identifier: Apache-2.0
//
// Convex hull clearing strategy for global voxel map integration.
// Computes the 3D convex hull of the incoming cloud, deletes existing
// voxels whose centroids lie strictly inside the hull (with configurable
// inset margin), then inserts the new points.

#ifndef STRATEGIES_HULL_CLEAR_HPP_
#define STRATEGIES_HULL_CLEAR_HPP_

#include <cmath>
#include <cstdio>
#include <vector>

#include <pcl/point_cloud.h>
#include <pcl/surface/convex_hull.h>

#include "voxel_map.hpp"

struct HullClearConfig {
    float margin = -1.0f;  // inset margin; negative = use voxel_size
};

/// Clear voxels inside the convex hull of `cloud`, then insert it.
template <typename PointT>
void hull_clear_and_insert(VoxelMap& map,
                           const typename pcl::PointCloud<PointT>::Ptr& cloud,
                           const HullClearConfig& cfg = {}) {
    if (!cloud || cloud->size() < 4) {
        map.insert<PointT>(cloud);
        return;
    }

    // Compute 3D convex hull
    pcl::ConvexHull<PointT> hull;
    hull.setInputCloud(cloud);
    hull.setDimension(3);

    typename pcl::PointCloud<PointT>::Ptr hull_vertices(new pcl::PointCloud<PointT>());
    std::vector<pcl::Vertices> hull_polygons;
    hull.reconstruct(*hull_vertices, hull_polygons);

    if (hull_polygons.empty() || hull_vertices->empty()) {
        map.insert<PointT>(cloud);
        return;
    }

    // Compute hull centroid for orienting normals outward
    float cx = 0, cy = 0, cz = 0;
    for (const auto& pt : hull_vertices->points) {
        cx += pt.x; cy += pt.y; cz += pt.z;
    }
    float inv_n = 1.0f / static_cast<float>(hull_vertices->size());
    cx *= inv_n; cy *= inv_n; cz *= inv_n;

    // Extract facet planes: each polygon -> outward normal + offset
    struct Plane {
        float nx, ny, nz, d;
    };

    std::vector<Plane> planes;
    planes.reserve(hull_polygons.size());

    for (const auto& polygon : hull_polygons) {
        if (polygon.vertices.size() < 3) continue;

        const auto& p0 = hull_vertices->points[polygon.vertices[0]];
        const auto& p1 = hull_vertices->points[polygon.vertices[1]];
        const auto& p2 = hull_vertices->points[polygon.vertices[2]];

        float e1x = p1.x - p0.x, e1y = p1.y - p0.y, e1z = p1.z - p0.z;
        float e2x = p2.x - p0.x, e2y = p2.y - p0.y, e2z = p2.z - p0.z;

        float nx = e1y * e2z - e1z * e2y;
        float ny = e1z * e2x - e1x * e2z;
        float nz = e1x * e2y - e1y * e2x;

        float len = std::sqrt(nx * nx + ny * ny + nz * nz);
        if (len < 1e-10f) continue;
        nx /= len; ny /= len; nz /= len;

        // Ensure normal points outward (away from centroid)
        float to_cx = cx - p0.x, to_cy = cy - p0.y, to_cz = cz - p0.z;
        if (nx * to_cx + ny * to_cy + nz * to_cz > 0) {
            nx = -nx; ny = -ny; nz = -nz;
        }

        planes.push_back({nx, ny, nz, nx * p0.x + ny * p0.y + nz * p0.z});
    }

    if (planes.empty()) {
        map.insert<PointT>(cloud);
        return;
    }

    // Shrink inward by margin so boundary voxels (surfaces) are preserved
    float margin = cfg.margin >= 0 ? cfg.margin : map.voxel_size();

    size_t cleared = 0;
    auto& m = map.data();
    for (auto it = m.begin(); it != m.end();) {
        const auto& v = it->second;
        bool inside = true;
        for (const auto& pl : planes) {
            if (pl.nx * v.x + pl.ny * v.y + pl.nz * v.z > pl.d - margin) {
                inside = false;
                break;
            }
        }
        if (inside) {
            it = m.erase(it);
            ++cleared;
        } else {
            ++it;
        }
    }

    if (cleared > 0) {
        printf("[hull_clear] %zu facets, cleared %zu voxels, map size %zu\n",
               planes.size(), cleared, map.size());
    }

    map.insert<PointT>(cloud);
}

#endif
