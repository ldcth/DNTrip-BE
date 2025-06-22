import json
import os
import re

def translate_vietnamese_to_english(text):
    """
    Removes Vietnamese diacritics from a string.
    """
    s = text.lower()
    s = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', s)
    s = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', s)
    s = re.sub(r'[ìíịỉĩ]', 'i', s)
    s = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', s)
    s = re.sub(r'[ùúụủũưừứựửữ]', 'u', s)
    s = re.sub(r'[ỳýỵỷỹ]', 'y', s)
    s = re.sub(r'[đ]', 'd', s)
    # Remove punctuation, but keep commas
    s = re.sub(r'[^\w\s,]', '', s)
    return s

def update_data_in_english():
    """
    Translates descriptions and addresses in the combined data file to English.
    """
    script_dir = os.path.dirname(__file__)
    data_file = os.path.join(script_dir, 'data', 'combined_data.json')

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}")
        return

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            places = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading {data_file}: {e}")
        return

    description_map = {
        "khu cắm trại": "campground",
        "nhà hàng": "restaurant",
        "nhà hàng việt nam": "restaurant",
        "nhà hàng ý": "restaurant",
        "nhà hàng thái lan": "restaurant",
        "nhà hàng cho người ăn chay": "restaurant",
        "nhà hàng tiệc đứng": "restaurant",
        "nhà hàng món nướng": "restaurant",
        "quán cà phê": "cafe",
        "quán cà phê nghệ thuật": "cafe",
        "quán bar": "bar",
        "quán bar karaoke": "bar",
        "quán bar cocktail": "bar",
        "bar thể thao": "bar",
        "quán bia": "bar",
        "tiệm bánh": "bakery",
        "cửa hàng bánh": "bakery",
        "siêu thị": "supermarket",
        "đại siêu thị": "supermarket",
        "trung tâm mua sắm": "shopping_mall",
        "cửa hàng": "store",
        "cửa hàng tiện lợi": "store",
        "cửa hàng tạp phẩm triều tiên": "store",
        "cửa hàng lưu niệm": "souvenir_store",
        "cửa hàng quà tặng": "souvenir_store",
        "cửa hàng quần áo": "clothing_store",
        "cửa hàng quần áo nam": "clothing_store",
        "cửa hàng quần áo nữ": "clothing_store",
        "cửa hàng quần áo cũ": "clothing_store",
        "cửa hàng quần áo cổ điển": "clothing_store",
        "cửa hàng phụ kiện thời trang": "store",
        "cửa hàng giày dép": "store",
        "cửa hàng giày thể thao": "store",
        "cửa hàng đồ da": "store",
        "cửa hàng điện thoại di động": "store",
        "bảo tàng": "museum",
        "bảo tàng lịch sử": "museum",
        "bảo tàng nghệ thuật": "art_gallery",
        "bảo tàng điêu khắc": "museum",
        "bảo tàng chiến tranh": "museum",
        "bảo tàng hàng hải": "museum",
        "bảo tàng di sản": "museum",
        "phòng trưng bày nghệ thuật": "art_gallery",
        "cửa hàng tranh": "art_gallery",
        "công viên": "park",
        "công viên giải trí": "amusement_park",
        "vườn bách thú": "zoo",
        "cửa hàng cá cảnh": "aquarium",
        "điểm thu hút khách du lịch": "tourist_attraction",
        "bảo tàng nghệ thuật": "art_gallery",
        "bảo tồn di sản": "tourist_attraction",
        "trung tâm nghệ thuật": "art_gallery",
        "trung tâm bán lẻ trực tiếp": "store",
        "cửa hàng bán thực phẩm đặc sản": "souvenir_store",
        "vườn": "park",
        "nghệ sĩ": "art_gallery",
        "trường nghệ thuật": "art_gallery",
        "phòng chờ": "lodging",
        "cầu": "tourist_attraction"
    }

    for place in places:
        # Translate description
        if 'description' in place and isinstance(place['description'], str):
            vietnamese_desc = place['description'].lower()
            english_desc = description_map.get(vietnamese_desc, place['description'])
            place['description'] = english_desc.replace("_", " ").title()
            place['category'] = english_desc

        # Translate address
        if 'address' in place and isinstance(place['address'], str):
            place['address'] = translate_vietnamese_to_english(place['address']).title()

    try:
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(places, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error writing to {data_file}: {e}")
        return

    print(f"Data translation complete for {data_file}")

if __name__ == "__main__":
    update_data_in_english() 