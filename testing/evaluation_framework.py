import json
import time
from typing import Dict, List, Any
from agents.intent_parser import parse_intent
from services.retriever_service import RetrieverService
from testing.comprehensive_test import (
    CATEGORY_QUERIES, CATEGORY_GROUND_TRUTH,
    SEMANTIC_QUERIES, SEMANTIC_GROUND_TRUTH,
    LOCATION_QUERIES, LOCATION_GROUND_TRUTH,
    DISTANCE_QUERIES, DISTANCE_GROUND_TRUTH,
    COMBINED_QUERIES, COMBINED_GROUND_TRUTH
)

class RetrievalEvaluator:
    def __init__(self):
        self.retriever = RetrieverService()
        self.results = {}
        
    def calculate_precision_at_k(self, retrieved: List[str], ground_truth: List[str], k: int = 5) -> float:
        """Calculate Precision@K"""
        if not retrieved:
            return 0.0
        
        retrieved_k = retrieved[:k]
        relevant_retrieved = sum(1 for item in retrieved_k if item in ground_truth)
        return relevant_retrieved / len(retrieved_k)
    
    def calculate_recall_at_k(self, retrieved: List[str], ground_truth: List[str], k: int = 5) -> float:
        """Calculate Recall@K"""
        if not ground_truth:
            return 0.0
        
        retrieved_k = retrieved[:k]
        relevant_retrieved = sum(1 for item in retrieved_k if item in ground_truth)
        return relevant_retrieved / len(ground_truth)
    
    def calculate_f1_score(self, precision: float, recall: float) -> float:
        """Calculate F1 Score"""
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)
    
    def calculate_mrr(self, retrieved: List[str], ground_truth: List[str]) -> float:
        """Calculate Mean Reciprocal Rank"""
        for i, item in enumerate(retrieved):
            if item in ground_truth:
                return 1.0 / (i + 1)
        return 0.0
    
    def evaluate_category_filtering(self) -> Dict[str, Any]:
        """Evaluate category-based filtering technique"""
        print("\n=== EVALUATING CATEGORY-BASED FILTERING ===")
        
        results = {
            "technique": "category_filtering",
            "queries": {},
            "avg_precision_at_5": 0.0,
            "avg_recall_at_5": 0.0,
            "avg_f1_score": 0.0,
            "avg_mrr": 0.0,
            "avg_response_time": 0.0,
            "total_queries": len(CATEGORY_QUERIES)
        }
        
        total_precision = total_recall = total_f1 = total_mrr = total_time = 0.0
        
        for q_id, query in CATEGORY_QUERIES.items():
            start_time = time.time()
            
            # Determine category from query
            category = self._extract_category_from_query(query)
            places = self.retriever.get_places_by_category(category)
            
            response_time = time.time() - start_time
            
            # Extract place names
            retrieved_names = [place.get('name') for place in places[:10]]
            ground_truth = CATEGORY_GROUND_TRUTH.get(q_id, [])
            
            # Calculate metrics
            precision = self.calculate_precision_at_k(retrieved_names, ground_truth, 5)
            recall = self.calculate_recall_at_k(retrieved_names, ground_truth, 5)
            f1 = self.calculate_f1_score(precision, recall)
            mrr = self.calculate_mrr(retrieved_names, ground_truth)
            
            results["queries"][q_id] = {
                "query": query,
                "precision_at_5": precision,
                "recall_at_5": recall,
                "f1_score": f1,
                "mrr": mrr,
                "response_time": response_time,
                "retrieved_count": len(places)
            }
            
            total_precision += precision
            total_recall += recall
            total_f1 += f1
            total_mrr += mrr
            total_time += response_time
            
            print(f"{q_id}: P@5={precision:.3f}, R@5={recall:.3f}, F1={f1:.3f}, MRR={mrr:.3f}")
        
        # Calculate averages
        num_queries = len(CATEGORY_QUERIES)
        results["avg_precision_at_5"] = total_precision / num_queries
        results["avg_recall_at_5"] = total_recall / num_queries
        results["avg_f1_score"] = total_f1 / num_queries
        results["avg_mrr"] = total_mrr / num_queries
        results["avg_response_time"] = total_time / num_queries
        
        return results
    
    def evaluate_semantic_search(self) -> Dict[str, Any]:
        """Evaluate semantic search technique"""
        print("\n=== EVALUATING SEMANTIC SEARCH ===")
        
        results = {
            "technique": "semantic_search",
            "queries": {},
            "avg_precision_at_5": 0.0,
            "avg_recall_at_5": 0.0,
            "avg_f1_score": 0.0,
            "avg_mrr": 0.0,
            "avg_response_time": 0.0,
            "total_queries": len(SEMANTIC_QUERIES)
        }
        
        total_precision = total_recall = total_f1 = total_mrr = total_time = 0.0
        
        for q_id, query in SEMANTIC_QUERIES.items():
            start_time = time.time()
            
            # Determine entity type
            entity_type = self._extract_entity_type_from_query(query)
            places = self.retriever.search_by_semantics(query, 10, entity_type)
            
            response_time = time.time() - start_time
            
            # Extract place names
            retrieved_names = [place.get('name') for place in places[:10]]
            ground_truth = SEMANTIC_GROUND_TRUTH.get(q_id, [])
            
            # Calculate metrics
            precision = self.calculate_precision_at_k(retrieved_names, ground_truth, 5)
            recall = self.calculate_recall_at_k(retrieved_names, ground_truth, 5)
            f1 = self.calculate_f1_score(precision, recall)
            mrr = self.calculate_mrr(retrieved_names, ground_truth)
            
            results["queries"][q_id] = {
                "query": query,
                "precision_at_5": precision,
                "recall_at_5": recall,
                "f1_score": f1,
                "mrr": mrr,
                "response_time": response_time,
                "retrieved_count": len(places)
            }
            
            total_precision += precision
            total_recall += recall
            total_f1 += f1
            total_mrr += mrr
            total_time += response_time
            
            print(f"{q_id}: P@5={precision:.3f}, R@5={recall:.3f}, F1={f1:.3f}, MRR={mrr:.3f}")
        
        # Calculate averages
        num_queries = len(SEMANTIC_QUERIES)
        results["avg_precision_at_5"] = total_precision / num_queries
        results["avg_recall_at_5"] = total_recall / num_queries
        results["avg_f1_score"] = total_f1 / num_queries
        results["avg_mrr"] = total_mrr / num_queries
        results["avg_response_time"] = total_time / num_queries
        
        return results
    
    def evaluate_location_filtering(self) -> Dict[str, Any]:
        """Evaluate location-based filtering technique"""
        print("\n=== EVALUATING LOCATION-BASED FILTERING ===")
        
        results = {
            "technique": "location_filtering",
            "queries": {},
            "avg_precision_at_5": 0.0,
            "avg_recall_at_5": 0.0,
            "avg_f1_score": 0.0,
            "avg_mrr": 0.0,
            "avg_response_time": 0.0,
            "total_queries": len(LOCATION_QUERIES)
        }
        
        total_precision = total_recall = total_f1 = total_mrr = total_time = 0.0
        
        for q_id, query in LOCATION_QUERIES.items():
            start_time = time.time()
            
            intent = parse_intent(query)
            places = self.retriever.retrieve_places({**intent, "top_k": 10})
            
            response_time = time.time() - start_time
            
            # Extract place names
            retrieved_names = [place.get('name') for place in places[:10]]
            ground_truth = LOCATION_GROUND_TRUTH.get(q_id, [])
            
            # Calculate metrics
            precision = self.calculate_precision_at_k(retrieved_names, ground_truth, 5)
            recall = self.calculate_recall_at_k(retrieved_names, ground_truth, 5)
            f1 = self.calculate_f1_score(precision, recall)
            mrr = self.calculate_mrr(retrieved_names, ground_truth)
            
            results["queries"][q_id] = {
                "query": query,
                "precision_at_5": precision,
                "recall_at_5": recall,
                "f1_score": f1,
                "mrr": mrr,
                "response_time": response_time,
                "retrieved_count": len(places)
            }
            
            total_precision += precision
            total_recall += recall
            total_f1 += f1
            total_mrr += mrr
            total_time += response_time
            
            print(f"{q_id}: P@5={precision:.3f}, R@5={recall:.3f}, F1={f1:.3f}, MRR={mrr:.3f}")
        
        # Calculate averages
        num_queries = len(LOCATION_QUERIES)
        results["avg_precision_at_5"] = total_precision / num_queries
        results["avg_recall_at_5"] = total_recall / num_queries
        results["avg_f1_score"] = total_f1 / num_queries
        results["avg_mrr"] = total_mrr / num_queries
        results["avg_response_time"] = total_time / num_queries
        
        return results
    
    def evaluate_distance_search(self) -> Dict[str, Any]:
        """Evaluate distance-based search technique"""
        print("\n=== EVALUATING DISTANCE-BASED SEARCH ===")
        
        results = {
            "technique": "distance_search",
            "queries": {},
            "avg_precision_at_5": 0.0,
            "avg_recall_at_5": 0.0,
            "avg_f1_score": 0.0,
            "avg_mrr": 0.0,
            "avg_response_time": 0.0,
            "total_queries": len(DISTANCE_QUERIES)
        }
        
        total_precision = total_recall = total_f1 = total_mrr = total_time = 0.0
        
        for q_id, query in DISTANCE_QUERIES.items():
            start_time = time.time()
            
            intent = parse_intent(query)
            places = self.retriever.retrieve_places({**intent, "top_k": 10})
            
            response_time = time.time() - start_time
            
            # Extract place names
            retrieved_names = [place.get('name') for place in places[:10]]
            ground_truth = DISTANCE_GROUND_TRUTH.get(q_id, [])
            
            # Calculate metrics
            precision = self.calculate_precision_at_k(retrieved_names, ground_truth, 5)
            recall = self.calculate_recall_at_k(retrieved_names, ground_truth, 5)
            f1 = self.calculate_f1_score(precision, recall)
            mrr = self.calculate_mrr(retrieved_names, ground_truth)
            
            results["queries"][q_id] = {
                "query": query,
                "precision_at_5": precision,
                "recall_at_5": recall,
                "f1_score": f1,
                "mrr": mrr,
                "response_time": response_time,
                "retrieved_count": len(places)
            }
            
            total_precision += precision
            total_recall += recall
            total_f1 += f1
            total_mrr += mrr
            total_time += response_time
            
            print(f"{q_id}: P@5={precision:.3f}, R@5={recall:.3f}, F1={f1:.3f}, MRR={mrr:.3f}")
        
        # Calculate averages
        num_queries = len(DISTANCE_QUERIES)
        results["avg_precision_at_5"] = total_precision / num_queries
        results["avg_recall_at_5"] = total_recall / num_queries
        results["avg_f1_score"] = total_f1 / num_queries
        results["avg_mrr"] = total_mrr / num_queries
        results["avg_response_time"] = total_time / num_queries
        
        return results
    
    def evaluate_combined_retrieval(self) -> Dict[str, Any]:
        """Evaluate combined intent-based retrieval technique"""
        print("\n=== EVALUATING COMBINED INTENT-BASED RETRIEVAL ===")
        
        results = {
            "technique": "combined_retrieval",
            "queries": {},
            "avg_precision_at_5": 0.0,
            "avg_recall_at_5": 0.0,
            "avg_f1_score": 0.0,
            "avg_mrr": 0.0,
            "avg_response_time": 0.0,
            "total_queries": len(COMBINED_QUERIES)
        }
        
        total_precision = total_recall = total_f1 = total_mrr = total_time = 0.0
        
        for q_id, query in COMBINED_QUERIES.items():
            start_time = time.time()
            
            intent = parse_intent(query)
            places = self.retriever.retrieve_places({**intent, "top_k": 10})
            
            response_time = time.time() - start_time
            
            # Extract place names
            retrieved_names = [place.get('name') for place in places[:10]]
            ground_truth = COMBINED_GROUND_TRUTH.get(q_id, [])
            
            # Calculate metrics
            precision = self.calculate_precision_at_k(retrieved_names, ground_truth, 5)
            recall = self.calculate_recall_at_k(retrieved_names, ground_truth, 5)
            f1 = self.calculate_f1_score(precision, recall)
            mrr = self.calculate_mrr(retrieved_names, ground_truth)
            
            results["queries"][q_id] = {
                "query": query,
                "precision_at_5": precision,
                "recall_at_5": recall,
                "f1_score": f1,
                "mrr": mrr,
                "response_time": response_time,
                "retrieved_count": len(places)
            }
            
            total_precision += precision
            total_recall += recall
            total_f1 += f1
            total_mrr += mrr
            total_time += response_time
            
            print(f"{q_id}: P@5={precision:.3f}, R@5={recall:.3f}, F1={f1:.3f}, MRR={mrr:.3f}")
        
        # Calculate averages
        num_queries = len(COMBINED_QUERIES)
        results["avg_precision_at_5"] = total_precision / num_queries
        results["avg_recall_at_5"] = total_recall / num_queries
        results["avg_f1_score"] = total_f1 / num_queries
        results["avg_mrr"] = total_mrr / num_queries
        results["avg_response_time"] = total_time / num_queries
        
        return results
    
    def _extract_category_from_query(self, query: str) -> str:
        """Extract category from query text"""
        query_lower = query.lower()
        if "restaurant" in query_lower:
            return "restaurant"
        elif "hotel" in query_lower:
            return "hotel"
        elif "cafe" in query_lower:
            return "cafe"
        elif "supermarket" in query_lower:
            return "supermarket"
        elif "bar" in query_lower:
            return "bar"
        elif "museum" in query_lower:
            return "museum"
        elif "art" in query_lower or "galleries" in query_lower:
            return "art_gallery"
        elif "bakery" in query_lower or "bakeries" in query_lower:
            return "bakery"
        elif "camping" in query_lower:
            return "campground"
        elif "tourist" in query_lower or "attraction" in query_lower:
            return "tourist_attraction"
        else:
            return None
    
    def _extract_entity_type_from_query(self, query: str) -> str:
        """Extract entity type from query text"""
        query_lower = query.lower()
        if "hotel" in query_lower or "resort" in query_lower:
            return "hotel"
        elif "restaurant" in query_lower or "dining" in query_lower:
            return "restaurant"
        elif "cafe" in query_lower or "coffee" in query_lower:
            return "cafe"
        elif "bar" in query_lower:
            return "bar"
        else:
            return None
    
    def run_full_evaluation(self) -> Dict[str, Any]:
        """Run complete evaluation of all retrieval techniques"""
        print("Starting comprehensive retrieval evaluation...")
        
        all_results = {
            "evaluation_summary": {
                "total_techniques": 5,
                "total_queries": (len(CATEGORY_QUERIES) + len(SEMANTIC_QUERIES) + 
                                len(LOCATION_QUERIES) + len(DISTANCE_QUERIES) + 
                                len(COMBINED_QUERIES)),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "technique_results": {}
        }
        
        # Evaluate each technique
        all_results["technique_results"]["category_filtering"] = self.evaluate_category_filtering()
        all_results["technique_results"]["semantic_search"] = self.evaluate_semantic_search()
        all_results["technique_results"]["location_filtering"] = self.evaluate_location_filtering()
        all_results["technique_results"]["distance_search"] = self.evaluate_distance_search()
        all_results["technique_results"]["combined_retrieval"] = self.evaluate_combined_retrieval()
        
        # Generate summary comparison
        self._generate_summary_comparison(all_results)
        
        return all_results
    
    def _generate_summary_comparison(self, results: Dict[str, Any]):
        """Generate summary comparison of all techniques"""
        print("\n" + "="*60)
        print("RETRIEVAL TECHNIQUES PERFORMANCE SUMMARY")
        print("="*60)
        
        techniques = results["technique_results"]
        
        print(f"{'Technique':<20} {'P@5':<8} {'R@5':<8} {'F1':<8} {'MRR':<8} {'Time(s)':<10}")
        print("-" * 60)
        
        for tech_name, tech_results in techniques.items():
            print(f"{tech_name:<20} "
                  f"{tech_results['avg_precision_at_5']:<8.3f} "
                  f"{tech_results['avg_recall_at_5']:<8.3f} "
                  f"{tech_results['avg_f1_score']:<8.3f} "
                  f"{tech_results['avg_mrr']:<8.3f} "
                  f"{tech_results['avg_response_time']:<10.4f}")
        
        print("\nLegend:")
        print("P@5: Precision at 5")
        print("R@5: Recall at 5")
        print("F1: F1 Score")
        print("MRR: Mean Reciprocal Rank")
        print("Time(s): Average response time in seconds")
        
    def save_results(self, results: Dict[str, Any], filename: str = "retrieval_evaluation_results.json"):
        """Save evaluation results to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {filename}")

def main():
    """Main evaluation function"""
    evaluator = RetrievalEvaluator()
    results = evaluator.run_full_evaluation()
    evaluator.save_results(results)

if __name__ == "__main__":
    main()