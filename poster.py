from PIL import Image, ImageDraw, ImageFont

def create_match_poster(team, opponent, date, time):

    img = Image.new("RGB", (800, 450), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    font_big = ImageFont.load_default()

    draw.text((200,100), team, fill="white", font=font_big)
    draw.text((350,200), "VS", fill="white", font=font_big)
    draw.text((200,300), opponent, fill="white", font=font_big)

    draw.text((50,400), f"{date} - {time}", fill="white", font=font_big)

    img.save("match.png")