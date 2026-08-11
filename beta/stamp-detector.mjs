const MAX_SIDE = 900;
const MAX_REGIONS = 80;

function colourDistance(a, b) {
  const dr = a[0] - b[0], dg = a[1] - b[1], db = a[2] - b[2];
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

function averageColours(samples) {
  if (!samples.length) return [255, 255, 255];
  const sum = samples.reduce((acc, c) => [acc[0] + c[0], acc[1] + c[1], acc[2] + c[2]], [0, 0, 0]);
  return sum.map(v => v / samples.length);
}

function cornerBackground(data, width, height) {
  const samples = [];
  const size = Math.max(4, Math.round(Math.min(width, height) * 0.045));
  const corners = [[0,0],[width-size,0],[0,height-size],[width-size,height-size]];
  const step = Math.max(1, Math.floor(size / 5));
  for (const [sx, sy] of corners) {
    for (let y = sy; y < sy + size; y += step) {
      for (let x = sx; x < sx + size; x += step) {
        const i = (y * width + x) * 4;
        samples.push([data[i], data[i+1], data[i+2]]);
      }
    }
  }
  return averageColours(samples);
}

function buildMask(imageData, width, height) {
  const {data} = imageData;
  const bg = cornerBackground(data, width, height);
  const raw = new Uint8Array(width * height);
  let mean = 0;
  for (let p = 0; p < width * height; p++) {
    const i = p * 4;
    mean += colourDistance([data[i], data[i+1], data[i+2]], bg);
  }
  mean /= width * height;
  const threshold = Math.max(28, Math.min(68, mean * 1.25));
  for (let p = 0; p < width * height; p++) {
    const i = p * 4;
    const r = data[i], g = data[i+1], b = data[i+2];
    const max = Math.max(r,g,b), min = Math.min(r,g,b);
    const saturation = max ? (max - min) / max : 0;
    const distance = colourDistance([r,g,b], bg);
    raw[p] = distance > threshold || (saturation > 0.18 && distance > threshold * 0.55) ? 1 : 0;
  }
  return raw;
}

function makeGrid(mask, width, height) {
  const cell = Math.max(4, Math.round(Math.min(width, height) / 120));
  const gw = Math.ceil(width / cell), gh = Math.ceil(height / cell);
  const grid = new Uint8Array(gw * gh);
  for (let gy = 0; gy < gh; gy++) for (let gx = 0; gx < gw; gx++) {
    let active = 0, total = 0;
    for (let y = gy * cell; y < Math.min(height, (gy + 1) * cell); y++) {
      for (let x = gx * cell; x < Math.min(width, (gx + 1) * cell); x++) {
        active += mask[y * width + x]; total++;
      }
    }
    grid[gy * gw + gx] = active / Math.max(1, total) > 0.16 ? 1 : 0;
  }
  return {grid, cell, gw, gh};
}

function connectedBoxes(grid, cell, gw, gh, width, height) {
  const seen = new Uint8Array(grid.length), boxes = [], stack = [];
  for (let sy = 0; sy < gh; sy++) for (let sx = 0; sx < gw; sx++) {
    const start = sy * gw + sx;
    if (!grid[start] || seen[start]) continue;
    let minX=sx,maxX=sx,minY=sy,maxY=sy,cells=0;
    seen[start]=1; stack.push(start);
    while (stack.length) {
      const pos=stack.pop(), x=pos%gw, y=Math.floor(pos/gw); cells++;
      minX=Math.min(minX,x); maxX=Math.max(maxX,x); minY=Math.min(minY,y); maxY=Math.max(maxY,y);
      for (const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        const nx=x+dx, ny=y+dy;
        if(nx<0||nx>=gw||ny<0||ny>=gh) continue;
        const np=ny*gw+nx;
        if(grid[np]&&!seen[np]){seen[np]=1;stack.push(np);}
      }
    }
    const bw=(maxX-minX+1)*cell, bh=(maxY-minY+1)*cell;
    const area=(bw*bh)/(width*height), aspect=bw/Math.max(1,bh);
    const boxCells=(maxX-minX+1)*(maxY-minY+1), density=cells/Math.max(1,boxCells);
    if(cells>=3&&area>=0.004&&area<=0.28&&aspect>=0.34&&aspect<=2.9&&bw>=width*0.04&&bh>=height*0.04&&density>=0.18){
      const pad=Math.max(2,Math.round(cell*0.75));
      const x=Math.max(0,minX*cell-pad), y=Math.max(0,minY*cell-pad);
      boxes.push({x,y,width:Math.min(width-x,bw+pad*2),height:Math.min(height-y,bh+pad*2),density});
    }
  }
  return boxes;
}

function intersection(a,b){
  const x1=Math.max(a.x,b.x),y1=Math.max(a.y,b.y),x2=Math.min(a.x+a.width,b.x+b.width),y2=Math.min(a.y+a.height,b.y+b.height);
  return Math.max(0,x2-x1)*Math.max(0,y2-y1);
}
function overlapRatio(a,b){const i=intersection(a,b);return i/Math.max(1,Math.min(a.width*a.height,b.width*b.height));}
function iou(a,b){const i=intersection(a,b);return i/Math.max(1,a.width*a.height+b.width*b.height-i);}

function removeOverlaps(boxes,width,height){
  const scored=boxes.map(box=>{
    const area=(box.width*box.height)/(width*height), aspect=box.width/Math.max(1,box.height);
    const areaPenalty=Math.max(0,area-0.11)*5;
    const extremePenalty=aspect<0.38||aspect>2.5?0.5:0;
    return {...box,score:box.density*2.2-areaPenalty-extremePenalty};
  }).sort((a,b)=>b.score-a.score);
  const kept=[];
  for(const box of scored){
    if(kept.some(other=>iou(box,other)>0.20||overlapRatio(box,other)>0.58)) continue;
    kept.push(box);
  }
  return kept.sort((a,b)=>a.y-b.y||a.x-b.x);
}

function findValley(values,start,end){
  let best=-1,bestValue=Infinity;
  const max=Math.max(1,...values);
  for(let i=Math.max(1,start);i<Math.min(values.length-1,end);i++){
    if(values[i]<bestValue&&values[i]<=Math.max(1,max*0.10)){best=i;bestValue=values[i];}
  }
  return best;
}

function splitLargeBox(box,grid,cell,gw,gh,width,height,depth=0){
  if(depth>=2) return [box];
  const gx0=Math.max(0,Math.floor(box.x/cell)), gx1=Math.min(gw,Math.ceil((box.x+box.width)/cell));
  const gy0=Math.max(0,Math.floor(box.y/cell)), gy1=Math.min(gh,Math.ceil((box.y+box.height)/cell));
  const cols=new Array(gx1-gx0).fill(0),rows=new Array(gy1-gy0).fill(0);
  for(let gy=gy0;gy<gy1;gy++) for(let gx=gx0;gx<gx1;gx++) if(grid[gy*gw+gx]){cols[gx-gx0]++;rows[gy-gy0]++;}
  const aspect=box.width/Math.max(1,box.height);
  let orientation=null,index=-1;
  if(aspect>1.25||box.width>width*0.22){index=findValley(cols,Math.floor(cols.length*0.22),Math.ceil(cols.length*0.78));if(index>0)orientation='v';}
  if(!orientation&&(aspect<0.55||box.height>height*0.24)){index=findValley(rows,Math.floor(rows.length*0.22),Math.ceil(rows.length*0.78));if(index>0)orientation='h';}
  if(!orientation)return [box];
  const cut=(orientation==='v'?gx0+index:gy0+index)*cell;
  let parts;
  if(orientation==='v') parts=[{...box,width:cut-box.x},{...box,x:cut,width:box.x+box.width-cut}];
  else parts=[{...box,height:cut-box.y},{...box,y:cut,height:box.y+box.height-cut}];
  if(parts.some(p=>p.width<width*0.04||p.height<height*0.04||(p.width*p.height)/(width*height)<0.004))return [box];
  return parts.flatMap(p=>splitLargeBox(p,grid,cell,gw,gh,width,height,depth+1));
}

function cropStats(ctx,box){
  const hashCanvas=document.createElement('canvas');hashCanvas.width=9;hashCanvas.height=8;
  const hc=hashCanvas.getContext('2d',{willReadFrequently:true});hc.drawImage(ctx.canvas,box.x,box.y,box.width,box.height,0,0,9,8);
  const hd=hc.getImageData(0,0,9,8).data;let bits='',r=0,g=0,b=0;const gray=[];
  for(let i=0;i<72;i++){const p=i*4;r+=hd[p];g+=hd[p+1];b+=hd[p+2];gray.push((hd[p]+hd[p+1]+hd[p+2])/3);}
  for(let y=0;y<8;y++)for(let x=0;x<8;x++)bits+=gray[y*9+x]>gray[y*9+x+1]?'1':'0';
  const sigCanvas=document.createElement('canvas');sigCanvas.width=8;sigCanvas.height=8;
  const sc=sigCanvas.getContext('2d',{willReadFrequently:true});sc.drawImage(ctx.canvas,box.x,box.y,box.width,box.height,0,0,8,8);
  const sd=sc.getImageData(0,0,8,8).data, signature=[];let mean=0;
  for(let i=0;i<64;i++){const p=i*4,v=(sd[p]+sd[p+1]+sd[p+2])/3;signature.push(v);mean+=v;} mean/=64;
  let variance=0;for(const v of signature)variance+=(v-mean)*(v-mean);const std=Math.sqrt(variance/64)||1;
  return {hash:bits,colour:[r/72,g/72,b/72],signature:signature.map(v=>(v-mean)/std)};
}
function hamming(a,b){let n=0;for(let i=0;i<Math.min(a.length,b.length);i++)if(a[i]!==b[i])n++;return n+Math.abs(a.length-b.length);}
function signatureDistance(a,b){let sum=0;for(let i=0;i<Math.min(a.length,b.length);i++){const d=a[i]-b[i];sum+=d*d;}return Math.sqrt(sum/Math.max(1,Math.min(a.length,b.length)));}

function consolidate(regions){
  const groups=[];
  for(const region of regions){
    const ratio=region.width/Math.max(1,region.height);
    const match=groups.find(g=>{
      const gr=g.width/Math.max(1,g.height);
      return Math.abs(gr-ratio)<=0.10&&hamming(g.hash,region.hash)<=7&&signatureDistance(g.signature,region.signature)<=0.42&&colourDistance(g.colour,region.colour)<=28;
    });
    if(match){match.quantity+=1;match.matches.push(region);}else groups.push({...region,quantity:1,matches:[region]});
  }
  return groups;
}

export async function detectStampGroups(blob){
  const bitmap=await createImageBitmap(blob);
  const scale=Math.min(1,MAX_SIDE/Math.max(bitmap.width,bitmap.height));
  const width=Math.max(1,Math.round(bitmap.width*scale)),height=Math.max(1,Math.round(bitmap.height*scale));
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(bitmap,0,0,width,height);bitmap.close?.();
  const mask=buildMask(ctx.getImageData(0,0,width,height),width,height);
  const {grid,cell,gw,gh}=makeGrid(mask,width,height);
  let boxes=connectedBoxes(grid,cell,gw,gh,width,height);
  boxes=removeOverlaps(boxes,width,height).flatMap(box=>splitLargeBox(box,grid,cell,gw,gh,width,height));
  boxes=removeOverlaps(boxes,width,height);
  if(!boxes.length||boxes.length>MAX_REGIONS)boxes=[{x:0,y:0,width,height,fallback:true,density:1}];
  const regions=boxes.map(box=>({...box,normalized:{x:box.x/width,y:box.y/height,width:box.width/width,height:box.height/height},...cropStats(ctx,box)}));
  const groups=consolidate(regions);
  return {groups,detected:!boxes[0]?.fallback,totalDetected:regions.length};
}
