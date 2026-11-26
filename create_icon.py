from PIL import Image, ImageDraw
from pathlib import Path

out = Path(__file__).parent / 'sijill.ico'
sizes = [16, 24, 32, 48, 64, 128, 256]
images = []
for n in sizes:
    im = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = n / 256
    def box(x0,y0,x1,y1,r,fill,outline=None,w=1):
        d.rounded_rectangle(tuple(round(v*s) for v in (x0,y0,x1,y1)), radius=round(r*s), fill=fill, outline=outline, width=max(1,round(w*s)))
    # deep navy rounded tile
    box(8,8,248,248,48,(15,31,55,255))
    # subtle blue inset panel
    box(22,22,234,234,38,(29,91,153,255))
    # document sheet
    box(60,42,181,164,13,(245,250,255,255))
    # folded corner
    d.polygon([(153* s,42*s),(181*s,70*s),(153*s,70*s)], fill=(173,216,245,255))
    # document lines
    for y, width in [(90,86),(112,68),(134,78)]:
        d.rounded_rectangle((78*s,y*s,(78+width)*s,(y+8)*s), radius=max(1,round(4*s)), fill=(79,143,202,255))
    # archive box base
    d.polygon([(48*s,151*s),(208*s,151*s),(194*s,207*s),(62*s,207*s)], fill=(17,155,160,255))
    d.line([(48*s,151*s),(208*s,151*s),(194*s,207*s),(62*s,207*s),(48*s,151*s)], fill=(197,244,239,255), width=max(1,round(5*s)), joint='curve')
    d.line([(128*s,151*s),(128*s,207*s)], fill=(197,244,239,255), width=max(1,round(4*s)))
    # lock/shield accent
    d.ellipse((100*s,164*s,156*s,220*s), fill=(15,31,55,255), outline=(255,255,255,255), width=max(1,round(3*s)))
    d.rounded_rectangle((113*s,151*s,143*s,180*s), radius=max(1,round(12*s)), outline=(255,255,255,255), width=max(1,round(6*s)))
    d.rectangle((120*s,177*s,136*s,192*s), fill=(255,255,255,255))
    images.append(im)
images[-1].save(out, format='ICO', sizes=[(n,n) for n in sizes], append_images=images[:-1])
# Also leave a preview for QA.
images[-1].save(Path(__file__).parent / 'sijill-icon-preview.png', format='PNG')
print(out)
