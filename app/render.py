"""CPU-only template renderer. Frames are composed with Pillow and encoded by FFmpeg."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

W,H=1920,1080
INK="#171c29"
PAPER="#f6f2e9"
ACCENT="#d4ff47"
FONT_REG=Path("C:/Windows/Fonts/segoeui.ttf")
FONT_BOLD=Path("C:/Windows/Fonts/segoeuib.ttf")


def font(size,bold=False):
    path=FONT_BOLD if bold else FONT_REG
    if path.exists(): return ImageFont.truetype(str(path),size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",size)


def fit(draw, value, width, max_size, bold=False):
    for size in range(max_size,25,-2):
        face=font(size,bold)
        if draw.textbbox((0,0),value,font=face)[2]<=width: return face
    return font(26,bold)


def base(kicker, index):
    canvas=Image.new("RGB",(W,H),PAPER)
    d=ImageDraw.Draw(canvas)
    d.rounded_rectangle((56,44,1864,1036),radius=34,fill=INK)
    d.text((110,94),"WORKDROP  /  STUDIO CUT",font=font(30,True),fill=ACCENT)
    d.text((1550,94),f"0{index} / 04",font=font(30),fill="#a6abbd")
    d.text((110,938),kicker.upper(),font=font(25,True),fill="#a6abbd")
    d.line((110,990,1810,990),fill="#666d7a",width=2)
    return canvas,d


def image_card(canvas,screenshot,box):
    d=ImageDraw.Draw(canvas)
    x0,y0,x1,y1=box
    d.rounded_rectangle((x0+20,y0+22,x1+20,y1+22),radius=28,fill="#070a10")
    d.rounded_rectangle(box,radius=28,fill="#ffffff")
    inset=18
    frame=(x1-x0-2*inset,y1-y0-2*inset)
    image=ImageOps.contain(screenshot,frame,method=Image.Resampling.LANCZOS)
    canvas.paste(image,(x0+inset+(frame[0]-image.width)//2,y0+inset+(frame[1]-image.height)//2))
    return d


def scenes(image,product,value,cta,directory):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    screenshot=Image.open(image).convert("RGB")
    outputs=[]
    c,d=base("From a screenshot to a story",1)
    d.text((116,232),"MEET",font=font(80,True),fill="#a8afb9")
    d.text((110,338),product,font=fit(d,product,1550,150,True),fill=PAPER)
    d.rounded_rectangle((112,620,880,746),radius=63,fill=ACCENT)
    d.text((159,652),"A PRODUCT WORTH SEEING",font=font(42,True),fill=INK)
    outputs.append(c)
    c,d=base("The product, in focus",2)
    image_card(c,screenshot,(956,204,1746,864))
    d.text((116,274),"THE",font=font(67,True),fill="#a8afb9")
    d.text((110,376),"BIG",font=font(128,True),fill=PAPER)
    d.text((110,535),"PICTURE.",font=font(128,True),fill=ACCENT)
    outputs.append(c)
    c,d=base("Why it matters",3)
    d.rounded_rectangle((117,234,1708,766),radius=40,fill="#2d3444")
    words=value.split(); lines=[]; line=""
    for word in words:
        trial=(line+" "+word).strip()
        if d.textbbox((0,0),trial,font=font(83,True))[2]>1430 and line:
            lines.append(line); line=word
        else: line=trial
    if line: lines.append(line)
    size=83 if len(lines)<=3 else 66
    for idx,line in enumerate(lines[:5]): d.text((170,310+idx*(size+24)),line,font=font(size,True),fill=PAPER)
    d.ellipse((1636,665,1688,717),fill=ACCENT)
    outputs.append(c)
    c,d=base("Take the next step",4)
    d.text((110,250),product,font=fit(d,product,1550,118,True),fill=PAPER)
    d.rounded_rectangle((110,519,1800,755),radius=48,fill=ACCENT)
    d.text((160,566),cta.upper(),font=fit(d,cta.upper(),1520,100,True),fill=INK)
    d.text((112,815),"MADE TO MOVE YOU FORWARD.",font=font(42,True),fill="#a8afb9")
    outputs.append(c)
    paths=[]
    for i,scene in enumerate(outputs):
        p=directory/f"scene-{i}.png"; scene.save(p,optimize=True); paths.append(p)
    return paths


def render(image, product, value, cta, output, scratch):
    start=time.monotonic()
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    paths=scenes(image,product,value,cta,scratch)
    temp=output.with_suffix(".rendering.mp4")
    args=["ffmpeg","-hide_banner","-loglevel","error","-y"]
    for path,duration in zip(paths,(4,4,4,3)):
        args += ["-loop","1","-framerate","30","-t",str(duration),"-i",str(path)]
    motion="".join((f"[{i}:v]zoompan=z='min(zoom+0.00025,1.04)':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s=1920x1080:fps=30[m{i}];" if i==1 else f"[{i}:v]fps=30[m{i}];") for i in range(4))
    args += ["-filter_complex",motion+"[m0][m1][m2][m3]concat=n=4:v=1:a=0,format=yuv420p[v]","-map","[v]","-frames:v","450","-c:v","libx264","-preset","veryfast","-crf","23","-movflags","+faststart","-an",str(temp)]
    subprocess.run(args,check=True,timeout=600,capture_output=True)
    check=probe(temp)
    if check["width"]!=W or check["height"]!=H or check["codec"]!="h264" or check["pixel_format"]!="yuv420p" or check["frames"]!=450 or abs(check["duration"]-15)>0.05:
        raise RuntimeError(f"Output contract failed: {check}")
    os.replace(temp,output)
    check["sha256"]=hashlib.sha256(output.read_bytes()).hexdigest()
    check["bytes"]=output.stat().st_size
    check["render_seconds"]=round(time.monotonic()-start,2)
    check["template"]="studio-cut-v1"
    return check


def probe(path):
    result=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,pix_fmt,width,height,nb_frames,r_frame_rate","-show_entries","format=duration","-of","json",str(path)],check=True,capture_output=True,text=True,timeout=30)
    data=json.loads(result.stdout); stream=data["streams"][0]
    return {"codec":stream["codec_name"],"pixel_format":stream["pix_fmt"],"width":stream["width"],"height":stream["height"],"frames":int(stream["nb_frames"]),"fps":stream["r_frame_rate"],"duration":float(data["format"]["duration"])}
