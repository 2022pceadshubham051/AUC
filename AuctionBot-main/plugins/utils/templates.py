from PIL import Image, ImageDraw, ImageOps
import io
import os

# Template dictionary (add more if needed)
TEMPLATES = {
    "auctionstart": {
        "path": "assets/auctionstart.png",  # background design
        "circle": {"x": 751, "y": 388, "size": 417}
    },
    "auctionsold": {
        "path": "assets/sold.png",  # background design
        "circle": {"x": 751, "y": 388, "size": 417}
    }
}

def generate_card(template_name, user_pfp=None, default_pfp="assets/default.png"):
    config = TEMPLATES[template_name]

    # Load template
    base = Image.open(config["path"]).convert("RGBA")

    # Profile picture
    if user_pfp and os.path.exists(user_pfp):
        pfp = Image.open(user_pfp).convert("RGBA")
    else:
        pfp = Image.open(default_pfp).convert("RGBA")

    # Circle values
    x, y, size = config["circle"]["x"], config["circle"]["y"], config["circle"]["size"]

    # Resize + make circular
    pfp = pfp.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    pfp.putalpha(mask)

    # Paste
    base.paste(pfp, (x, y), pfp)

    # Return as BytesIO
    bio = io.BytesIO()
    bio.name = "card.png"
    base.save(bio, "PNG")
    bio.seek(0)
    return bio
