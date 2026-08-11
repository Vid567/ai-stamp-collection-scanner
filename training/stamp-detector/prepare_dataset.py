from pathlib import Path
import argparse, hashlib, shutil

EXT={'.jpg','.jpeg','.png','.webp'}
def bucket(name):
    n=int(hashlib.sha256(name.encode()).hexdigest()[:8],16)%100
    return 'train' if n<70 else 'val' if n<90 else 'test'
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='training/stamp-detector/source');p.add_argument('--out',default='training/stamp-detector/dataset');a=p.parse_args();src,out=Path(a.source),Path(a.out)
    pairs=[]
    for image in sorted(src.iterdir() if src.exists() else []):
        if image.suffix.lower() not in EXT: continue
        label=image.with_suffix('.txt')
        if not label.exists(): print('SKIP no label:',image.name);continue
        split=bucket(image.stem);pairs.append((image,label,split))
    for image,label,split in pairs:
        idir=out/'images'/split;ldir=out/'labels'/split;idir.mkdir(parents=True,exist_ok=True);ldir.mkdir(parents=True,exist_ok=True)
        shutil.copy2(image,idir/image.name);shutil.copy2(label,ldir/label.name)
    counts={s:sum(1 for *_,x in pairs if x==s) for s in ('train','val','test')}
    print('Prepared',len(pairs),'annotated images:',counts)
if __name__=='__main__':main()
