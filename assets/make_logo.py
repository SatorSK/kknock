"""kknock 대표 이미지(600x600 PNG) 생성 — v2.

4배 슈퍼샘플링으로 그린 뒤 축소해 엣지를 부드럽게 처리한다.
컨셉: 다크 배경 위 옐로 채팅버블("똑똑") + 타이핑 인디케이터 버블.
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 4  # supersample
W = H = 600 * S

INK = (20, 20, 24)
YELLOW = (255, 205, 10)
YELLOW_DEEP = (255, 176, 0)
GRAY = (168, 168, 178)

# ---- 배경: 세로 그라데이션 (짙은 차콜)
img = Image.new("RGB", (W, H))
top, bot = (26, 26, 32), (15, 15, 19)
for y in range(H):
    t = y / H
    img.paste(
        tuple(int(a + (b - a) * t) for a, b in zip(top, bot)),
        (0, y, W, y + 1),
    )
d = ImageDraw.Draw(img)

def rounded_with_shadow(box, radius, fill, shadow_offset=10 * S // 4, blur=18 * S // 4):
    """그림자 딸린 라운드 사각형."""
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sb = [box[0], box[1] + shadow_offset, box[2], box[3] + shadow_offset]
    sd.rounded_rectangle(sb, radius=radius, fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    img.paste(shadow, (0, 0), shadow)
    d.rounded_rectangle(box, radius=radius, fill=fill)

# ---- 메인 버블 (옐로 그라데이션 흉내: 두 톤 겹치기)
bx0, by0, bx1, by1 = 92 * S, 118 * S, 508 * S, 338 * S
rounded_with_shadow([bx0, by0, bx1, by1], radius=56 * S, fill=YELLOW)
# 아래쪽에 살짝 딥옐로 하이라이트 라인
d.rounded_rectangle(
    [bx0, by1 - 26 * S, bx1, by1], radius=13 * S, fill=YELLOW_DEEP
)
d.rounded_rectangle([bx0, by0, bx1, by1 - 8 * S], radius=56 * S, fill=YELLOW)

# 버블 꼬리 (왼쪽 아래, 곡선 느낌의 삼각형)
d.polygon(
    [(150 * S, by1 - 14 * S), (218 * S, by1 - 4 * S), (138 * S, by1 + 52 * S)],
    fill=YELLOW,
)

# ---- "똑똑" 타이포
font_big = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 128 * S)
text = "똑똑"
tb = d.textbbox((0, 0), text, font=font_big)
tw, th = tb[2] - tb[0], tb[3] - tb[1]
cx = (bx0 + bx1) / 2
cy = (by0 + by1) / 2 - 4 * S
d.text((cx - tw / 2 - tb[0], cy - th / 2 - tb[1]), text, font=font_big, fill=INK)

# ---- 타이핑 인디케이터 버블 (오른쪽 아래, 응답 중인 에이전트)
tx0, ty0, tx1, ty1 = 340 * S, 372 * S, 508 * S, 452 * S
rounded_with_shadow([tx0, ty0, tx1, ty1], radius=40 * S, fill=(38, 38, 46))
dot_y = (ty0 + ty1) / 2
for i, dx in enumerate((-38, 0, 38)):
    r = 11 * S
    alpha = [GRAY, (210, 210, 218), YELLOW][i]
    x = (tx0 + tx1) / 2 + dx * S
    d.ellipse([x - r, dot_y - r, x + r, dot_y + r], fill=alpha)

# ---- 워드마크
font_mid = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 40 * S)
font_small = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 24 * S)

wm = "kknock"
tb = d.textbbox((0, 0), wm, font=font_mid)
d.text(((W - (tb[2] - tb[0])) / 2 - tb[0], 476 * S), wm, font=font_mid, fill=(245, 245, 248))
sub = "캠퍼스 공지 에이전트"
tb = d.textbbox((0, 0), sub, font=font_small)
d.text(((W - (tb[2] - tb[0])) / 2 - tb[0], 534 * S), sub, font=font_small, fill=GRAY)

# ---- 다운스케일 & 저장
final = img.resize((600, 600), Image.LANCZOS)
final.save("C:/AI/claude/kknock/assets/kknock_logo.png")
print("saved", final.size)
