import torch


def resolve_device():
    """
    Pick the torch device for YOLO inference.

    CUDA is used when available (a RunPod GPU box, or an NVIDIA-equipped Windows/Linux
    machine). Everywhere else - including Apple Silicon - this deliberately falls back to
    CPU rather than "mps": several ops this pipeline depends on (torchvision's NMS among
    them) are not implemented for the MPS backend, so requesting it outright breaks
    inference instead of just running slower.
    """
    return "cuda" if torch.cuda.is_available() else "cpu"
