import os
import qrcode

def generate_qr_codes(base_url: str, out_dir: str = "assets"):
    os.makedirs(out_dir, exist_ok=True)
    for desk_id in range(1, 16):
        url = f"{base_url}/?checkin={desk_id}"
        img = qrcode.make(url)
        img.save(os.path.join(out_dir, f"qr_desk_{desk_id}.png"))
