"""
Qt and PIL Image conversion utilities for FGOA.

Modern Pillow (10.0+) dropped PyQt5 support in `PIL.ImageQt`, only supporting
PyQt6 and PySide6. This module provides robust, high-performance, and safe
conversions between PIL Images and PyQt5 QImage / QPixmap.
"""
from io import BytesIO
from typing import Optional
from PIL import Image
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QBuffer, QIODevice


def pil_to_qimage(pil_img: Optional[Image.Image]) -> QImage:
    """
    Convert a PIL Image to a PyQt5 QImage.
    Ensures memory ownership is detached so the returned QImage is safe to use.
    """
    if pil_img is None:
        return QImage()

    if pil_img.mode != "RGBA":
        rgba_img = pil_img.convert("RGBA")
    else:
        rgba_img = pil_img

    data = rgba_img.tobytes("raw", "RGBA")
    qim = QImage(
        data,
        rgba_img.width,
        rgba_img.height,
        rgba_img.width * 4,
        QImage.Format_RGBA8888,
    )
    # Detach from python buffer by making a deep copy
    return qim.copy()


def pil_to_qpixmap(pil_img: Optional[Image.Image]) -> QPixmap:
    """
    Convert a PIL Image to a PyQt5 QPixmap.
    """
    if pil_img is None:
        return QPixmap()
    qim = pil_to_qimage(pil_img)
    return QPixmap.fromImage(qim)


def qimage_to_pil(qimg: Optional[QImage]) -> Optional[Image.Image]:
    """
    Convert a PyQt5 QImage to a PIL Image (RGBA).
    """
    if qimg is None or qimg.isNull():
        return None

    try:
        converted = qimg.convertToFormat(QImage.Format_RGBA8888)
        width = converted.width()
        height = converted.height()
        stride = converted.bytesPerLine()
        ptr = converted.bits()
        ptr.setsize(height * stride)
        return Image.frombytes("RGBA", (width, height), bytes(ptr), "raw", "RGBA", stride, 1)
    except Exception:
        # Fallback via QBuffer PNG
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        qimg.save(buf, "PNG")
        raw = bytes(buf.data())
        buf.close()
        return Image.open(BytesIO(raw))


def qpixmap_to_pil(qpix: Optional[QPixmap]) -> Optional[Image.Image]:
    """
    Convert a PyQt5 QPixmap to a PIL Image (RGBA).
    """
    if qpix is None or qpix.isNull():
        return None
    return qimage_to_pil(qpix.toImage())


class ImageQt(QImage):
    """
    PyQt5 drop-in replacement for PIL.ImageQt.ImageQt.
    """

    def __init__(self, pil_img: Image.Image):
        qim = pil_to_qimage(pil_img)
        super().__init__(qim)

    @staticmethod
    def fromqimage(im: QImage) -> Optional[Image.Image]:
        return qimage_to_pil(im)

    @staticmethod
    def fromqpixmap(im: QPixmap) -> Optional[Image.Image]:
        return qpixmap_to_pil(im)


# Top-level module aliases for drop-in PIL.ImageQt compatibility
fromqimage = qimage_to_pil
fromqpixmap = qpixmap_to_pil
toqimage = pil_to_qimage
toqpixmap = pil_to_qpixmap
