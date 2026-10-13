'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-06 22:39:03
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-06 22:39:04
FilePath: /Differentiable-3D-Partitioner/partitioner/utils/visualize.py
Description: Visualize z values over xy for a single iteration
'''
import torch
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize


def visualize_z_single(x_coords,
                       y_coords,
                       z_values,
                       iteration,
                       save_path=None,
                       node_size_x=None,
                       node_size_y=None,
                       die_xl=None,
                       die_yl=None,
                       die_xh=None,
                       die_yh=None):
    """
    visualize z values over xy for a single iteration
    
    Args:
        x_coords: x coordinates, shape [num_nodes] tensor or numpy array
        y_coords: y coordinates, shape [num_nodes] tensor or numpy array
        z_values: z values, shape [num_nodes] tensor or numpy array
        iteration: current iteration number
        save_path: save path (optional)
        node_size_x: x size of each node, shape [num_nodes] tensor or numpy array (optional)
        node_size_y: y size of each node, shape [num_nodes] tensor or numpy array (optional)
        die_xl: die left boundary (optional)
        die_yl: die bottom boundary (optional)
        die_xh: die right boundary (optional)
        die_yh: die top boundary (optional)
    """
    # convert to numpy array
    if isinstance(x_coords, torch.Tensor):
        x_coords = x_coords.detach().cpu().numpy()
    if isinstance(y_coords, torch.Tensor):
        y_coords = y_coords.detach().cpu().numpy()
    if isinstance(z_values, torch.Tensor):
        z_values = z_values.detach().cpu().numpy()
    if node_size_x is not None and isinstance(node_size_x, torch.Tensor):
        node_size_x = node_size_x.detach().cpu().numpy()
    if node_size_y is not None and isinstance(node_size_y, torch.Tensor):
        node_size_y = node_size_y.detach().cpu().numpy()

    # create single 3D plot
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')

    # get colormap
    cmap = plt.cm.get_cmap('RdYlBu_r')

    # normalize z values for color mapping
    z_normalized = (z_values - z_values.min()) / (z_values.max() -
                                                  z_values.min() + 1e-8)

    # if node sizes are provided, draw rectangles; otherwise draw scatter points
    if node_size_x is not None and node_size_y is not None:
        # draw 2D rectangular planes for each node at their z height
        all_faces = []
        all_colors = []

        for i in range(len(x_coords)):
            x = x_coords[i]
            y = y_coords[i]
            z = z_values[i]
            size_x = node_size_x[i]
            size_y = node_size_y[i]

            # calculate rectangle corners (bottom-left origin)
            x_min = x
            x_max = x + size_x
            y_min = y
            y_max = y + size_y

            # create a single 2D rectangular plane at z height (parallel to XY plane)
            rect_face = [[x_min, y_min, z], [x_max, y_min, z],
                         [x_max, y_max, z], [x_min, y_max, z]]

            all_faces.append(rect_face)

            # get color for this node based on z value
            color = cmap(z_normalized[i])
            all_colors.append(color)

        # create Poly3DCollection
        collection = Poly3DCollection(all_faces,
                                      facecolors=all_colors,
                                      edgecolors='k',
                                      linewidths=0.2,
                                      alpha=0.7)
        ax.add_collection3d(collection)

        # create a mappable for colorbar
        norm = Normalize(vmin=z_values.min(), vmax=z_values.max())
        scatter = ScalarMappable(norm=norm, cmap='RdYlBu_r')
        scatter.set_array([])
    else:
        # fallback to scatter plot if node sizes not provided
        scatter = ax.scatter(x_coords,
                             y_coords,
                             z_values,
                             c=z_values,
                             cmap='RdYlBu_r',
                             s=20,
                             alpha=0.6,
                             edgecolors='k',
                             linewidths=0.3)

    ax.set_xlabel('X Coordinate', fontsize=12)
    ax.set_ylabel('Y Coordinate', fontsize=12)
    ax.set_zlabel('Z Value (Soft Assignment)', fontsize=12)
    ax.set_title(f'Iteration {iteration} - Z Distribution over XY',
                 fontsize=14,
                 fontweight='bold')
    ax.set_zlim(0, 1)

    if die_xl is not None and die_xh is not None:
        ax.set_xlim(die_xl, die_xh)
    if die_yl is not None and die_yh is not None:
        ax.set_ylim(die_yl, die_yh)

    plt.colorbar(scatter, ax=ax, shrink=0.8, label='Z Value')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"visualization saved to: {save_path}")

    plt.close()
