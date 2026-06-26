from ultralytics import YOLO

model = YOLO("models/best.pt")

results = model.predict("input_videos/08fd33_4.mp4", save=True)
print(results[0])

print("************************************")

for box in results[0].boxes:
    print(box)


# Load the model
# model = YOLO("yolov8x").to(device)
# print("before: ", model.device.type)

# # model = YOLO("yolov8x")


# print results below

# boxes: ultralytics.engine.results.Boxes object
# keypoints: None
# masks: None
# names: {0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane', 5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light', 10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench', 14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow', 20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe', 24: 'backpack', 25: 'umbrella', 26: 'handbag', 27: 'tie', 28: 'suitcase', 29: 'frisbee', 30: 'skis', 31: 'snowboard', 32: 'sports ball', 33: 'kite', 34: 'baseball bat', 35: 'baseball glove', 36: 'skateboard', 37: 'surfboard', 38: 'tennis racket', 39: 'bottle', 40: 'wine glass', 41: 'cup', 42: 'fork', 43: 'knife', 44: 'spoon', 45: 'bowl', 46: 'banana', 47: 'apple', 48: 'sandwich', 49: 'orange', 50: 'broccoli', 51: 'carrot', 52: 'hot dog', 53: 'pizza', 54: 'donut', 55: 'cake', 56: 'chair', 57: 'couch', 58: 'potted plant', 59: 'bed', 60: 'dining table', 61: 'toilet', 62: 'tv', 63: 'laptop', 64: 'mouse', 65: 'remote', 66: 'keyboard', 67: 'cell phone', 68: 'microwave', 69: 'oven', 70: 'toaster', 71: 'sink', 72: 'refrigerator', 73: 'book', 74: 'clock', 75: 'vase', 76: 'scissors', 77: 'teddy bear', 78: 'hair drier', 79: 'toothbrush'}
# obb: None
# orig_img: array([[[100, 146, 105],
#         [ 92, 138,  97],
#         [ 97, 150, 101],
#         ...,
#         [100,  92,  82],
#         [103,  95,  85],
#         [105,  97,  87]],

#        [[ 99, 145, 104],
#         [ 99, 145, 104],
#         [109, 162, 113],
#         ...,
#         [105,  97,  87],
#         [107,  99,  89],
#         [108, 100,  90]],

#        [[ 96, 149, 100],
#         [105, 158, 109],
#         [112, 170, 113],
#         ...,
#         [106,  98,  88],
#         [108, 100,  90],
#         [110, 102,  92]],

#        ...,

#        [[ 74, 103,  78],
#         [ 74, 103,  78],
#         [ 74, 103,  78],
#         ...,
#         [ 30,  47,  43],
#         [ 31,  48,  44],
#         [ 31,  48,  44]],

#        [[ 74, 103,  78],
#         [ 74, 103,  78],
#         [ 74, 103,  78],
#         ...,
#         [ 44,  56,  55],
#         [ 46,  58,  57],
#         [ 46,  58,  57]],

#        [[ 74, 103,  78],
#         [ 74, 103,  78],
#         [ 74, 103,  78],
#         ...,
#         [ 48,  60,  59],
#         [ 49,  61,  60],
#         [ 49,  61,  60]]], dtype=uint8)
# orig_shape: (1080, 1920)
# path: 'D:\\code\\ml\\footballanalysis\\input_videos\\08fd33_4.mp4'
# probs: None
# save_dir: 'runs\\detect\\predict'
# speed: {'preprocess': 10.532855987548828, 'inference': 2026.9925594329834, 'postprocess': 1414.2725467681885}
# ************************************


# cls: tensor([0.]) cls is class id and this tensor defines that it is for a person as seen in the output
# conf: tensor([0.8626]) -  confidence score which means that the model is 86% confident that the object is a person
# data: tensor([[533.7254, 686.3998, 579.3201, 784.5262,   0.8626,   0.0000]])
# id: None
# is_track: False
# orig_shape: (1080, 1920)
# shape: torch.Size([1, 6])
# xywh: tensor([[556.5228, 735.4630,  45.5947,  98.1264]])
# xywhn: tensor([[0.2899, 0.6810, 0.0237, 0.0909]])
# xyxy: tensor([[533.7254, 686.3998, 579.3201, 784.5262]])
# xyxyn: tensor([[0.2780, 0.6356, 0.3017, 0.7264]])
# ultralytics.engine.results.Boxes object with attributes:
