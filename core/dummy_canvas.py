"""
Dummy Canvas Generator for FGOA.
Creates a realistic mock/virtual application screen with coordinate grid and distinct UI elements
when the live target application is not bound or not running.
"""
from typing import Optional
from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont, QPixmap
from PyQt5.QtCore import Qt, QRect, QPoint
from PIL import Image


def create_dummy_canvas_qimage(width: int = 1600, height: int = 900) -> QImage:
    """
    Creates a high-resolution virtual canvas QImage with:
    - Slate dark theme background
    - Precise 50px / 100px coordinate grid lines & coordinate labels
    - Top title bar indicating resolution and dummy mode
    - Distinct colored UI elements (buttons, cards, badges) for color picking & testing
    - Bottom navigation bar
    """
    w = max(400, int(width) if width else 1600)
    h = max(300, int(height) if height else 900)

    image = QImage(w, h, QImage.Format_RGB32)
    image.fill(QColor(30, 41, 59))  # Slate dark #1e293b

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # 1. Subtle Background Grid (50px fine grid, 100px main grid)
    pen_subtle = QPen(QColor(51, 65, 85, 120), 1, Qt.DotLine)
    pen_main = QPen(QColor(71, 85, 105, 180), 1, Qt.SolidLine)
    font_grid = QFont("Arial", 8)
    painter.setFont(font_grid)

    # Vertical grid lines
    for x in range(0, w, 50):
        if x % 100 == 0:
            painter.setPen(pen_main)
            painter.drawLine(x, 40, x, h - 50)
            painter.setPen(QColor(148, 163, 184, 160))
            painter.drawText(x + 2, 54, str(x))
        else:
            painter.setPen(pen_subtle)
            painter.drawLine(x, 40, x, h - 50)

    # Horizontal grid lines
    for y in range(0, h, 50):
        if y % 100 == 0:
            painter.setPen(pen_main)
            painter.drawLine(0, y, w, y)
            painter.setPen(QColor(148, 163, 184, 160))
            if y >= 60:
                painter.drawText(4, y - 3, str(y))
        else:
            painter.setPen(pen_subtle)
            painter.drawLine(0, y, w, y)

    # 2. Top Header Bar
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(15, 23, 42)))  # #0f172a
    painter.drawRect(0, 0, w, 40)
    painter.setPen(QPen(QColor(51, 65, 85), 1))
    painter.drawLine(0, 40, w, 40)

    # Header window control dots
    dots = [(QColor(239, 68, 68), 16), (QColor(245, 158, 11), 32), (QColor(34, 197, 94), 48)]
    for color, cx in dots:
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(cx, 20), 5, 5)

    # Header Title
    painter.setPen(QColor(56, 189, 248))  # #38bdf8
    painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
    painter.drawText(66, 25, f"🎮 [가상 타겟 화면 (더미 캔버스)]  해상도: {w} × {h}")

    # 3. Center Watermark
    painter.setPen(QColor(100, 116, 139, 130))
    painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
    watermark_rect = QRect(0, int(h * 0.45) - 30, w, 60)
    painter.drawText(watermark_rect, Qt.AlignCenter, "더미 테스트 캔버스 (타겟 앱 미지정 가상 모드)")

    painter.setFont(QFont("Segoe UI", 10))
    painter.setPen(QColor(148, 163, 184, 120))
    subtext_rect = QRect(0, int(h * 0.45) + 30, w, 30)
    painter.drawText(subtext_rect, Qt.AlignCenter, "인식 조건 포인트 설정, 컬러 피커 및 액션 시퀀스 테스트가 가능합니다.")

    # 4. Interactive Colored UI Mockups (Distinct Colors for Reliable Color-Picking)
    # Row 1: Action Buttons
    btn_y = 70
    btn_h = 44
    btn_w = min(140, int(w * 0.12))

    buttons = [
        ("확인 / 실행", QColor(22, 163, 74), QColor(34, 197, 94)),     # Green #16a34a
        ("정보 / 메뉴", QColor(37, 99, 235), QColor(59, 130, 246)),    # Blue #2563eb
        ("취소 / 정지", QColor(220, 38, 38), QColor(239, 68, 68)),    # Red #dc2626
        ("★ 보상 / 샵", QColor(202, 138, 4), QColor(234, 179, 8)),    # Gold #ca8a04
    ]

    bx = int(w * 0.08)
    for title, bg_col, border_col in buttons:
        painter.setPen(QPen(border_col, 2))
        painter.setBrush(QBrush(bg_col))
        painter.drawRoundedRect(bx, btn_y, btn_w, btn_h, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QRect(bx, btn_y, btn_w, btn_h), Qt.AlignCenter, title)
        bx += btn_w + 20

    # Row 2: Mock Game / Quest Cards
    card_y = 150
    card_w = min(260, int(w * 0.22))
    card_h = min(280, int(h * 0.38))

    cards = [
        ("퀘스트 A (보라)", QColor(124, 58, 237), QColor(147, 51, 234), "(7c3aed)"),  # Purple
        ("퀘스트 B (청록)", QColor(8, 145, 178), QColor(6, 182, 212), "(0891b2)"),   # Cyan
        ("퀘스트 C (주황)", QColor(234, 88, 12), QColor(249, 115, 22), "(ea580c)"),  # Orange
    ]

    cx = int(w * 0.08)
    for title, bg_col, border_col, hex_code in cards:
        if cx + card_w > w:
            break
        painter.setPen(QPen(border_col, 2))
        painter.setBrush(QBrush(bg_col))
        painter.drawRoundedRect(cx, card_y, card_w, card_h, 8, 8)

        # Card Title
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(QRect(cx, card_y + 16, card_w, 24), Qt.AlignCenter, title)

        # Subtext / Color Code
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor(241, 245, 249, 200))
        painter.drawText(QRect(cx, card_y + 44, card_w, 20), Qt.AlignCenter, hex_code)

        # Inner action target area
        inner_w = card_w - 40
        inner_h = 36
        inner_x = cx + 20
        inner_y = card_y + card_h - 50
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
        painter.drawRoundedRect(inner_x, inner_y, inner_w, inner_h, 4, 4)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QRect(inner_x, inner_y, inner_w, inner_h), Qt.AlignCenter, "선택 / 클릭")

        cx += card_w + 30

    # 5. Bottom Navigation Bar
    bar_h = 50
    bar_y = h - bar_h
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(15, 23, 42)))  # #0f172a
    painter.drawRect(0, bar_y, w, bar_h)
    painter.setPen(QPen(QColor(51, 65, 85), 1))
    painter.drawLine(0, bar_y, w, bar_y)

    nav_tabs = ["🏠 홈", "⚔️ 배틀", "📦 인벤토리", "⚙️ 설정"]
    tab_w = min(120, int(w / len(nav_tabs)))
    for idx, tab_name in enumerate(nav_tabs):
        tx = int((w - len(nav_tabs) * tab_w) / 2) + idx * tab_w
        painter.setPen(QColor(203, 213, 225))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRect(tx, bar_y, tab_w, bar_h), Qt.AlignCenter, tab_name)

    painter.end()
    return image


def create_dummy_canvas_pixmap(width: int = 1600, height: int = 900) -> QPixmap:
    """Creates dummy canvas as QPixmap."""
    qimg = create_dummy_canvas_qimage(width, height)
    return QPixmap.fromImage(qimg)


def create_dummy_canvas_pil(width: int = 1600, height: int = 900) -> Image.Image:
    """Creates dummy canvas as PIL RGBA Image."""
    from ui.qt_image_utils import qimage_to_pil
    qimg = create_dummy_canvas_qimage(width, height)
    pil_img = qimage_to_pil(qimg)
    if pil_img is None:
        # Fallback raw RGBA
        return Image.new("RGBA", (max(400, width), max(300, height)), (30, 41, 59, 255))
    return pil_img
