import os
import json

def clean_and_combine_data():
    """
    Cleans phone number data in JSON files and combines them into a single file.
    """
    script_dir = os.path.dirname(__file__)
    data_dir = os.path.join(script_dir, 'data', 'gg')
    output_file = os.path.join(script_dir, 'data', 'combined_data.json')
    
    all_places = []

    if not os.path.exists(data_dir):
        print(f"Directory not found: {data_dir}")
        return

    for filename in os.listdir(data_dir):
        if filename.endswith('.json'):
            file_path = os.path.join(data_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    places = json.load(f)
                
                for place in places:
                    if 'phone' in place and isinstance(place.get('phone'), str) and place['phone'].startswith('\n'):
                        place['phone'] = 'N/A'
                
                all_places.extend(places)
                print(f"Processed {filename}")

            except (json.JSONDecodeError, IOError) as e:
                print(f"Error processing {filename}: {e}")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_places, f, ensure_ascii=False, indent=2)

    print(f"\nAll data combined and saved to {output_file}")
    print(f"Total places combined: {len(all_places)}")

if __name__ == "__main__":
    clean_and_combine_data() 