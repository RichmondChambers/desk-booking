import qrcode
from io import BytesIO
from PIL import Image

def generate_qr(url: str) -> Image.Image:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make()
    img = qr.make_image(fill_color="black", back_color="white")
    return img
