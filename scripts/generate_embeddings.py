import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

def generate_embeddings():
    """
    Generates embeddings for place descriptions and saves them to a FAISS index.
    """
    print("Starting embedding generation...")
    
    data_path = "scrapper/data"
    output_path = "scrapper/data"
    
    # 1. Load all relevant data
    all_places = []
    for filename in ["combined_data.json", "tripadvisor_da_nang_final_details.json"]:
        file_path = os.path.join(data_path, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Add a source identifier to each place
                for item in data:
                    item['source_file'] = filename
                all_places.extend(data)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load {filename}. Skipping.")
    
    if not all_places:
        print("Error: No data found to process. Exiting.")
        return

    # 2. Extract descriptions to be encoded
    descriptions = [place.get("description", "") for place in all_places]
    print(f"Found {len(descriptions)} descriptions to encode.")

    # 3. Load a pre-trained sentence transformer model
    print("Loading SentenceTransformer model...")
    # 'all-MiniLM-L6-v2' is a good starting point: fast and effective.
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # 4. Generate embeddings
    print("Generating embeddings for descriptions. This may take a moment...")
    embeddings = model.encode(descriptions, show_progress_bar=True)
    
    # Ensure embeddings are in a 2D numpy array of type float32 for FAISS
    embeddings = np.array(embeddings).astype('float32')
    
    # 5. Build a FAISS index
    embedding_dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(embedding_dimension)
    index.add(embeddings)
    
    # 6. Save the index and the mapping
    index_path = os.path.join(output_path, "semantic_index.faiss")
    mapping_path = os.path.join(output_path, "semantic_mapping.json")
    
    faiss.write_index(index, index_path)
    
    # Create a simple mapping from index position to original data identifier
    # This helps us retrieve the full data after a search
    mapping = {i: {
        "name": place.get("name"), 
        "source": place.get("source_file")
    } for i, place in enumerate(all_places)}
    
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated and saved FAISS index to: {index_path}")
    print(f"Successfully saved data mapping to: {mapping_path}")

if __name__ == "__main__":
    # Ensure the output directory exists
    os.makedirs("scrapper/data", exist_ok=True)
    generate_embeddings() 