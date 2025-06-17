import ir_measures
from ir_measures import AP, P, RR, nDCG
from agents.intent_parser import parse_intent
from services.retriever_service import RetrieverService

# Define a central set of test queries with unique IDs
QUERIES = {
    "q1": "top 3 restaurants in hải châu",
    "q2": "find a hotel near the beach",
    "q3": "top 3 restaurants near Fivitel Da Nang Hotel",
    "q4": "find a hotel with cozy room",
    "q5": "find a hotel with a pool",
    "q6": "find top 5 supermarkets in hai chau"
}

# Define a central ground truth mapping using the same query IDs.
GROUND_TRUTH = {
    "q1": [
        "Nhà hàng Nhà Gỗ Đà Nẵng", "Au Restaurant", "TOM82 DANANG Restaurant - 다낭 똠팔이",
        "Quán Huế Ngon - 다낭최고의 로컬 BBQ 레스토랑- Best local food in Da Nang",
        "Nhà Hàng Đồ Ăn Thái - Thai Market Restaurant - Trần Quốc Toản", "Ăn Thôi",
        "The View - Yacht Restaurant Da Nang", "Nhà Hàng Phì Lũ 1", "NHÀ HÀNG HỒNG NGỌC",
        "City High Dining", "Nhà Hàng New Sky - New Sky Restaurant"
    ],
    "q2": [
        "HAIAN Beach Hotel & Spa", "White Sand Boutique Hotel", "Danang Marriott Resort & Spa",
        "Sandy Beach Non Nuoc Resort"
    ],
    "q3": [
        "The View - Yacht Restaurant Da Nang",
        "Nhà Hàng Đồ Ăn Thái - Thai Market Restaurant - Trần Quốc Toản",
        "TOM82 DANANG Restaurant - 다낭 똠팔이"
    ],
    "q4": [
        "Danang Marriott Resort & Spa",
        "Cozy Danang Boutique Hotel",
    ],
    "q5": [
        "Danang Marriott Resort & Spa",
        "Cozy Danang Boutique Hotel",
    ],
    "q6": [
        "Danang Marriott Resort & Spa",
        "Cozy Danang Boutique Hotel",
    ]
}

def main_test_and_evaluate():
    """
    Runs all test queries, collects the results, and then performs a single
    evaluation at the end, printing a per-query report.
    """
    retriever = RetrieverService()
    all_runs = []
    
    print("--- Running All Test Queries ---")
    for q_id, query in QUERIES.items():
        print(f"\nExecuting RAG query ({q_id}): '{query}'")
        intent = parse_intent(query)
        print(f"  -> Parsed Intent: {intent}")
        
        places = retriever.retrieve_places({**intent, "top_k": 10})
        
        print(f"  -> Retrieved {len(places)} places. Top 5:")
        for i, place in enumerate(places[:5]):
            print(f"     {i+1}. {place.get('name')}")
            
        # Add this query's results to our master list for evaluation
        for i, place in enumerate(places):
            score = len(places) - i  # Create a descending score based on rank
            all_runs.append(ir_measures.ScoredDoc(q_id, place.get("name"), score))

    print("\n\n--- Overall Evaluation ---")
    
    # Create the complete ground truth object
    all_qrels = [ir_measures.Qrel(qid, doc, 1) for qid, docs in GROUND_TRUTH.items() for doc in docs]
    
    # Define measures
    measures = [P@3, RR, AP, nDCG@5]
    
    # Use iter_calc to get per-query results in one go
    results_iterator = ir_measures.iter_calc(measures, all_qrels, all_runs)
    
    # Group results by query for clean printing
    per_query_results = {}
    for metric in results_iterator:
        if metric.query_id not in per_query_results:
            per_query_results[metric.query_id] = {}
        per_query_results[metric.query_id][str(metric.measure)] = metric.value
        
    # Print the final report
    for q_id, scores in sorted(per_query_results.items()):
        print(f"\n--- Statistics for Query ({q_id}): '{QUERIES[q_id]}' ---")
        for measure_name, value in scores.items():
            print(f"  {measure_name:<8}: {value:.4f}")

if __name__ == "__main__":
    main_test_and_evaluate() 