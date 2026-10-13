'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-05 16:56:01
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-09 17:19:55
FilePath: /Differentiable-3D-Partitioner/partitioner/utils/tensor2txt.py
Description: Write a tensor to a txt file line by line
'''
import torch
import numpy as np
from typing import Union


def tensor2txt(tensor: Union[torch.Tensor, np.ndarray],
               output_path: str,
               precision: int = 6,
               delimiter: str = ' ',
               fmt: str = None) -> None:
    """
    Write tensor to a txt file line by line
    
    Args:
        tensor: Input tensor, can be a PyTorch tensor or numpy array
        output_path: Output file path
        precision: Floating point precision (number of decimal places), default 6
        delimiter: Delimiter, default is space
        fmt: Format string; if None it will be selected automatically, e.g. '%.6f' or '%d'
    
    Examples:
        >>> import torch
        >>> import numpy as np
        >>> 
        >>> # PyTorch tensor
        >>> t = torch.tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        >>> tensor2txt(t, 'output.txt')
        >>> 
        >>> # Numpy array
        >>> arr = np.array([[1, 2, 3], [4, 5, 6]])
        >>> tensor2txt(arr, 'output.txt', fmt='%d')
    """
    # Convert to numpy array
    if isinstance(tensor, torch.Tensor):
        array = tensor.detach().cpu().numpy()
    elif isinstance(tensor, np.ndarray):
        array = tensor.copy()
    else:
        raise TypeError(f"不支持的类型: {type(tensor)}，需要 torch.Tensor 或 np.ndarray")

    # Flatten to a 2D array (if the dimension is higher, flatten all dimensions except the first)
    if array.ndim == 0:
        # Scalar
        array = array.reshape(1, 1)
    elif array.ndim == 1:
        # 1D array, convert to 2D (one element per row)
        array = array.reshape(-1, 1)
    elif array.ndim > 2:
        # High-dimensional array, flatten all dimensions except the first)
        original_shape = array.shape
        array = array.reshape(original_shape[0], -1)

    # Determine format string
    if fmt is None:
        if np.issubdtype(array.dtype, np.integer):
            fmt = f'%d'
        else:
            fmt = f'%.{precision}f'

    # Write to file line by line
    with open(output_path, 'w', encoding='utf-8') as f:
        for row in array:
            # Convert each row to string and join with the specified delimiter
            row_str = delimiter.join([fmt % val for val in row])
            f.write(row_str + '\n')


def tensor2txt_simple(tensor: Union[torch.Tensor, np.ndarray],
                      output_path: str) -> None:
    """
    Simplified version: write tensor to txt file line by line (using default settings)
    
    Args:
        tensor: Input tensor, can be a PyTorch tensor or numpy array
        output_path: Output file path
    """
    tensor2txt(tensor, output_path)


if __name__ == '__main__':
    # Example usage
    import os

    # # Example 1: PyTorch 2D tensor
    # print("Example 1: PyTorch 2D tensor")
    # t1 = torch.tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    # tensor2txt(t1, 'test_output_1.txt')
    # print(f"Saved to test_output_1.txt")

    # # Example 2: Numpy 1D array
    # print("\nExample 2: Numpy 1D array")
    # arr1 = np.array([1, 2, 3, 4, 5])
    # tensor2txt(arr1, 'test_output_2.txt', fmt='%d')
    # print(f"Saved to test_output_2.txt")

    # # Example 3: high precision floating point numbers
    # print("\nExample 3: high precision floating point numbers")
    # arr2 = np.random.rand(5, 3)
    # tensor2txt(arr2, 'test_output_3.txt', precision=8)
    # print(f"Saved to test_output_3.txt")

    # # Example 4: using comma as delimiter
    # print("\nExample 4: using comma as delimiter")
    # arr3 = np.array([[1.1, 2.2, 3.3], [4.4, 5.5, 6.6]])
    # tensor2txt(arr3, 'test_output_4.txt', delimiter=',', precision=2)
    # print(f"Saved to test_output_4.txt")

    tensor2txt(torch.load("results/aes/binary_assignment.pt"),
               'results/aes/binary_assignment.txt')
    print("\nfinished")
