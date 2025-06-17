import ir_measures
from ir_measures import AP, nDCG, P, RR
from services.retriever_service import RetrieverService
from agents.intent_parser import parse_intent

def define_ground_truth():
    """
    Defines a set of test queries and the expected "relevant" documents for each.
    This is our hand-labeled "correct" data in the format ir-measures expects.
    """
    queries = {
        "q1": "top restaurants in hải châu",
        "q2": "a hotel near the beach",
        "q3": "restaurants near Furama Resort Danang"
    }
    
    # A list of Qrel objects. Relevance is binary (1 for relevant, 0 for not).
    qrels = [
        # For q1, all restaurants in Hai Chau are relevant.
        ir_measures.Qrel("q1", "Nhà hàng Nhà Gỗ Đà Nẵng", 1),
        ir_measures.Qrel("q1", "Au Restaurant", 1),
        ir_measures.Qrel("q1", "TOM82 DANANG Restaurant - 다낭 똠팔이", 1),
        ir_measures.Qrel("q1", "Quán Huế Ngon - 다낭최고의 로컬 BBQ 레스토랑- Best local food in Da Nang", 1),
        ir_measures.Qrel("q1", "Nhà Hàng Đồ Ăn Thái - Thai Market Restaurant - Trần Quốc Toản", 1),
        ir_measures.Qrel("q1", "Ăn Thôi", 1),
        ir_measures.Qrel("q1", "The View - Yacht Restaurant Da Nang", 1),
        ir_measures.Qrel("q1", "Nhà Hàng Phì Lũ 1", 1),
        ir_measures.Qrel("q1", "NHÀ HÀNG HỒNG NGỌC", 1),
        ir_measures.Qrel("q1", "City High Dining", 1),
        ir_measures.Qrel("q1", "Nhà Hàng New Sky - New Sky Restaurant", 1),

        # For q2, only hotels with "beach" in their description are relevant.
        ir_measures.Qrel("q2", "Minh Toan Athena Hotel", 1),
        ir_measures.Qrel("q2", "Furama Resort Danang", 1),
        ir_measures.Qrel("q2", "Son Tra Resort & Spa Danang", 1),
        ir_measures.Qrel("q2", "Sandy Beach Non Nuoc Resort", 1),
    ]
    return queries, qrels

def run_evaluation():
    """
    Runs the retriever against the ground truth and prints evaluation metrics
    using the ir-measures library.
    """
    queries, qrels = define_ground_truth()
    retriever = RetrieverService()
    
    # Store the results from our system in the format ir-measures expects.
    run = []

    print("Running queries through the retriever...")
    for q_id, query in queries.items():
        print(f"  - Running query ({q_id}): '{query}'")
        intent = parse_intent(query)
        places = retriever.retrieve_places({**intent, "top_k": 15})
        
        # Convert our results into a list of ScoredDoc objects
        for i, place in enumerate(places):
            # The score should be descending. We can use the rank as a proxy.
            score = len(places) - i
            run.append(ir_measures.ScoredDoc(q_id, place.get("name"), score))
    
    print("\n--- Evaluation Metrics (using ir-measures) ---")
    
    # Define the set of measures to calculate
    measures = [
        AP,         # Average Precision (MAP when aggregated)
        RR,         # Reciprocal Rank (MRR when aggregated)
        P@5,        # Precision at 5
        nDCG@10,    # Normalized Discounted Cumulative Gain at 10
    ]
    
    # Calculate and print all metrics
    results = ir_measures.calc_aggregate(measures, qrels, run)
    
    for measure, value in results.items():
        print(f"{str(measure):<10}: {value:.4f}")

if __name__ == "__main__":
    run_evaluation() 