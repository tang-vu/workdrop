"""Create original sample input and the shipped, playable product teaser."""
from pathlib import Path
from PIL import Image, ImageDraw
from app.render import render, font

root=Path("assets/sample"); root.mkdir(parents=True,exist_ok=True)
image=Image.new("RGB",(1440,900),"#eae6db")
d=ImageDraw.Draw(image)
d.rounded_rectangle((85,80,1355,820),radius=34,fill="#fbfaf7")
d.text((135,130),"AURA",font=font(58,True),fill="#17202c")
d.text((1050,153),"SHOP   ABOUT   CART",font=font(22,True),fill="#17202c")
d.rounded_rectangle((135,265,685,748),radius=25,fill="#d8e8dc")
d.ellipse((270,342,550,622),fill="#abc7a8")
d.ellipse((333,312,490,660),fill="#f8f5ea",outline="#667b65",width=10)
d.text((760,315),"A calmer day",font=font(60,True),fill="#17202c")
d.text((760,405),"starts here.",font=font(60,True),fill="#17202c")
d.text((760,535),"A simple ritual for a clearer mind.",font=font(24),fill="#637078")
d.rounded_rectangle((760,615,1230,690),radius=37,fill="#17202c")
d.text((802,630),"EXPLORE THE COLLECTION",font=font(27,True),fill="#ffffff")
source=root/"aura-product-screenshot.png"; image.save(source)
meta=render(source,"Aura","A calmer daily ritual, designed to help you focus on what matters.","Explore Aura",root/"workdrop-sample.mp4",root/"frames")
print(meta)
