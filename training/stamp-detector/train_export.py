from pathlib import Path
import argparse, shutil

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default='yolo11n.pt');p.add_argument('--epochs',type=int,default=100);p.add_argument('--imgsz',type=int,default=640);p.add_argument('--device',default=None);a=p.parse_args()
    try: from ultralytics import YOLO
    except ImportError: raise SystemExit('Install training dependency first: pip install ultralytics')
    root=Path(__file__).resolve().parents[2];data=root/'training/stamp-detector/data.yaml';dest=root/'beta/models/stamp-detector.onnx'
    model=YOLO(a.model);kwargs=dict(data=str(data),epochs=a.epochs,imgsz=a.imgsz,patience=20,project=str(root/'training/stamp-detector/runs'),name='stamp-v1',exist_ok=True)
    if a.device: kwargs['device']=a.device
    result=model.train(**kwargs);best=Path(result.save_dir)/'weights/best.pt';trained=YOLO(str(best));metrics=trained.val(data=str(data),split='test' if (root/'training/stamp-detector/dataset/images/test').exists() else 'val')
    print('Validation complete:',metrics.results_dict)
    exported=Path(trained.export(format='onnx',imgsz=a.imgsz,simplify=True,nms=False,dynamic=False));dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(exported,dest);print('ONNX model copied to',dest)
if __name__=='__main__':main()
