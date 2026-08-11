const MAX_SIDE = 720;

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
  const size = Math.max(3, Math.round(Math.min(width, height) * 0.04));
  const corners = [[0,0],[width-size,0],[0,height-size],[width-size,height-size]];
  for (const [sx, sy] of corners) {
    for (let y = sy; y < sy + size; y += Math.max(1, Math.floor(size / 4))) {
      for (let x = sx; x < sx + size; x += Math.max(1, Math.floor(size / 4))) {
        const i = (y * width + x) * 4;
        samples.push([data[i], data[i+1], data[i+2]]);
      }
    }
  }
  return averageColours(samples);
}

function buildMask(imageData, width, height) {
  const bg = cornerBackground(imageData.data, width, height);
  const raw = new Uint8Array(width * height);
  let mean = 0;
  for (let p = 0; p < width * height; p++) {
    const i = p * 4;
    const d = colourDistance([imageData.data[i], imageData.data[i+1], imageData.data[i+2]], bg);
    mean += d;
  }
  mean /= width * height;
  const threshold = Math.max(32, Math.min(72, mean * 1.35));
  for (let p = 0; p < width * height; p++) {
    const i = p * 4;
    const d = colourDistance([imageData.data[i], imageData.data[i+1], imageData.data[i+2]], bg);
    raw[p] = d > threshold ? 1 : 0;
  }
  return raw;
}

function coarseComponents(mask, width, height) {
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
    grid[gy * gw + gx] = active / Math.max(1, total) > 0.18 ? 1 : 0;
  }

  // Small dilation joins the artwork/text inside one physical stamp.
  const dilated = new Uint8Array(grid.length);
  for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) {
    let on = 0;
    for (let dy = -1; dy <= 1 && !on; dy++) for (let dx = -1; dx <= 1; dx++) {
      const nx = x + dx, ny = y + dy;
      if (nx >= 0 && nx < gw && ny >= 0 && ny < gh && grid[ny * gw + nx]) { on = 1; break; }
    }
    dilated[y * gw + x] = on;
  }

  const seen = new Uint8Array(dilated.length);
  const boxes = [];
  const stack = [];
  for (let sy = 0; sy < gh; sy++) for (let sx = 0; sx < gw; sx++) {
    const start = sy * gw + sx;
    if (!dilated[start] || seen[start]) continue;
    let minX = sx, maxX = sx, minY = sy, maxY = sy, cells = 0;
    seen[start] = 1; stack.push(start);
    while (stack.length) {
      const pos = stack.pop(), x = pos % gw, y = Math.floor(pos / gw); cells++;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      for (const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        const nx=x+dx, ny=y+dy;
        if (nx<0||nx>=gw||ny<0||ny>=gh) continue;
        const np=ny*gw+nx;
        if (dilated[np] && !seen[np]) { seen[np]=1; stack.push(np); }
      }
    }
    const bw=(maxX-minX+1)*cell, bh=(maxY-minY+1)*cell;
    const area=(bw*bh)/(width*height), aspect=bw/Math.max(1,bh);
    if (cells >= 4 && area >= 0.008 && area <= 0.45 && aspect >= 0.42 && aspect <= 2.4 && bw >= width*0.055 && bh >= height*0.055) {
      const pad=Math.round(cell*1.5);
      boxes.push({x:Math.max(0,minX*cell-pad),y:Math.max(0,minY*cell-pad),width:Math.min(width-minX*cell+pad,bw+pad*2),height:Math.min(height-minY*cell+pad,bh+pad*2)});
    }
  }
  return boxes.sort((a,b)=>a.y-b.y || a.x-b.x);
}

function cropStats(ctx, box) {
  const canvas = document.createElement('canvas'); canvas.width = 9; canvas.height = 8;
  const c = canvas.getContext('2d', {willReadFrequently:true});
  c.drawImage(ctx.canvas, box.x, box.y, box.width, box.height, 0, 0, 9, 8);
  const d = c.getImageData(0,0,9,8).data;
  let bits = '', r=0,g=0,b=0;
  const gray=[];
  for (let i=0;i<72;i++) { const p=i*4; r+=d[p];g+=d[p+1];b+=d[p+2];gray.push((d[p]+d[p+1]+d[p+2])/3); }
  for (let y=0;y<8;y++) for (let x=0;x<8;x++) bits += gray[y*9+x] > gray[y*9+x+1] ? '1':'0';
  return {hash:bits, colour:[r/72,g/72,b/72]};
}

function hamming(a,b) { let n=0; for(let i=0;i<Math.min(a.length,b.length);i++) if(a[i]!==b[i]) n++; return n + Math.abs(a.length-b.length); }

function consolidate(regions) {
  const groups=[];
  for (const region of regions) {
    const match=groups.find(g => hamming(g.hash,region.hash) <= 2 && colourDistance(g.colour,region.colour) <= 14 && Math.abs((g.width/g.height)-(region.width/region.height)) <= 0.12);
    if (match) { match.quantity += 1; match.matches.push(region); }
    else groups.push({...region, quantity:1, matches:[region]});
  }
  return groups;
}

export async function detectStampGroups(blob) {
  const bitmap = await createImageBitmap(blob);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale)), height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas=document.createElement('canvas'); canvas.width=width; canvas.height=height;
  const ctx=canvas.getContext('2d',{willReadFrequently:true}); ctx.drawImage(bitmap,0,0,width,height); bitmap.close?.();
  const imageData=ctx.getImageData(0,0,width,height);
  let boxes=coarseComponents(buildMask(imageData,width,height),width,height);
  if (!boxes.length) boxes=[{x:0,y:0,width,height,fallback:true}];
  // Avoid obviously fragmented detections; a conservative fallback is better than dozens of false rows.
  if (boxes.length > 24) boxes=[{x:0,y:0,width,height,fallback:true}];
  const regions=boxes.map(box=>({
    ...box,
    normalized:{x:box.x/width,y:box.y/height,width:box.width/width,height:box.height/height},
    ...cropStats(ctx,box)
  }));
  const groups=consolidate(regions);
  return {groups, detected: !boxes[0]?.fallback, totalDetected: regions.length};
}
