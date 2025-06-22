 # Comprehensive Retrieval Test Datasets

This document describes the comprehensive test datasets created for evaluating each retrieval technique in the `RetrieverService`. Each technique has 10 carefully designed test cases based on actual data from `combined_data.json` and `tripadvisor_da_nang_final_details.json`.

## Overview

The test datasets are organized into 5 categories, each targeting a specific retrieval technique:

1. **Category-Based Filtering** (10 queries)
2. **Semantic Search** (10 queries)  
3. **Location-Based Filtering** (10 queries)
4. **Distance-Based Search** (10 queries)
5. **Combined Intent-Based Retrieval** (10 queries)

**Total: 50 test queries across all techniques**

## 1. Category-Based Filtering Test Dataset

**Purpose**: Test the `get_places_by_category()` method and `restaurants` property.

**Test Cases**:
- `cat_q1`: "show me all restaurants" → Tests restaurant category filtering
- `cat_q2`: "find hotels in da nang" → Tests hotel category filtering
- `cat_q3`: "list all cafes" → Tests cafe category filtering
- `cat_q4`: "show supermarkets" → Tests supermarket category filtering
- `cat_q5`: "find bars and pubs" → Tests bar category filtering
- `cat_q6`: "museums in the area" → Tests museum category filtering
- `cat_q7`: "art galleries" → Tests art gallery category filtering
- `cat_q8`: "show me bakeries" → Tests bakery category filtering
- `cat_q9`: "find camping grounds" → Tests campground category filtering
- `cat_q10`: "tourist attractions" → Tests tourist attraction category filtering

**Ground Truth**: Contains actual place names from the datasets for each category (10 places per category).

## 2. Semantic Search Test Dataset

**Purpose**: Test the `search_by_semantics()` method with complex descriptive queries.

**Test Cases**:
- `sem_q1`: "romantic dinner restaurant with river view" → Tests semantic understanding of atmosphere + location
- `sem_q2`: "luxury beachfront hotel with spa facilities" → Tests semantic understanding of luxury + amenities
- `sem_q3`: "cozy coffee shop for working" → Tests semantic understanding of workspace-friendly cafes
- `sem_q4`: "fresh seafood restaurant near beach" → Tests semantic understanding of cuisine + location
- `sem_q5`: "budget friendly hotel downtown" → Tests semantic understanding of price + location
- `sem_q6`: "rooftop bar with city view" → Tests semantic understanding of venue type + view
- `sem_q7`: "traditional vietnamese cuisine" → Tests semantic understanding of cuisine type
- `sem_q8`: "family friendly resort with pool" → Tests semantic understanding of family amenities
- `sem_q9`: "trendy cafe with good wifi" → Tests semantic understanding of modern amenities
- `sem_q10`: "fine dining michelin restaurant" → Tests semantic understanding of high-end dining

**Ground Truth**: Contains places that semantically match the query intent based on descriptions and features.

## 3. Location-Based Filtering Test Dataset

**Purpose**: Test location filtering functionality in `retrieve_places()` method.

**Test Cases**:
- `loc_q1`: "restaurants in hai chau district" → Tests district-level filtering
- `loc_q2`: "hotels on vo nguyen giap street" → Tests street-level filtering
- `loc_q3`: "cafes in son tra peninsula" → Tests area-level filtering
- `loc_q4`: "bars on bach dang street" → Tests specific street filtering
- `loc_q5`: "museums in hai chau" → Tests district + category filtering
- `loc_q6`: "shopping in ngu hanh son" → Tests district + activity filtering
- `loc_q7`: "restaurants on tran phu street" → Tests street + category filtering
- `loc_q8`: "hotels near my khe beach" → Tests landmark-based filtering
- `loc_q9`: "cafes in thanh khe district" → Tests district + category filtering
- `loc_q10`: "supermarkets in cam le district" → Tests district + category filtering

**Ground Truth**: Contains places that are actually located in the specified areas based on address data.

## 4. Distance-Based Search Test Dataset

**Purpose**: Test distance calculation and proximity search functionality.

**Test Cases**:
- `dist_q1`: "restaurants near Dragon Bridge" → Tests proximity to major landmark
- `dist_q2`: "hotels near Da Nang Airport" → Tests proximity to transportation hub
- `dist_q3`: "cafes near Han Market" → Tests proximity to market area
- `dist_q4`: "bars near My Khe Beach" → Tests proximity to beach area
- `dist_q5`: "museums near Cham Museum" → Tests proximity to cultural landmark
- `dist_q6`: "restaurants near Marble Mountains" → Tests proximity to tourist attraction
- `dist_q7`: "hotels near Intercontinental Resort" → Tests proximity to luxury resort
- `dist_q8`: "cafes near Vincom Plaza" → Tests proximity to shopping center
- `dist_q9`: "supermarkets near Lotte Mart" → Tests proximity to major store
- `dist_q10`: "restaurants near Danang Cathedral" → Tests proximity to religious landmark

**Ground Truth**: Contains places that are geographically close to the reference points based on coordinates.

## 5. Combined Intent-Based Retrieval Test Dataset

**Purpose**: Test the full `retrieve_places()` method with complex multi-criteria queries.

**Test Cases**:
- `comb_q1`: "top 5 luxury hotels with ocean view and spa" → Tests ranking + amenities + view
- `comb_q2`: "best vietnamese restaurants in hai chau with high rating" → Tests cuisine + location + quality
- `comb_q3`: "rooftop bars near dragon bridge with city view" → Tests venue type + proximity + view
- `comb_q4`: "family restaurants with outdoor seating near beach" → Tests family-friendly + amenities + location
- `comb_q5`: "boutique hotels in downtown with pool facilities" → Tests hotel type + location + amenities
- `comb_q6`: "traditional cafes in old quarter with local atmosphere" → Tests atmosphere + location + authenticity
- `comb_q7`: "seafood restaurants within 2km of marble mountains" → Tests cuisine + distance constraint
- `comb_q8`: "budget hotels near airport with free wifi" → Tests price + location + amenities
- `comb_q9`: "art galleries and museums in cultural district" → Tests multiple categories + cultural area
- `comb_q10`: "convenience stores and supermarkets open 24 hours" → Tests multiple categories + operating hours

**Ground Truth**: Contains places that satisfy multiple criteria from the complex queries.

## Evaluation Metrics

Each test case is evaluated using standard information retrieval metrics:

- **Precision@5**: Relevance of top 5 results
- **Recall@5**: Coverage of relevant items in top 5 results
- **F1 Score**: Harmonic mean of precision and recall
- **Mean Reciprocal Rank (MRR)**: Average of reciprocal ranks of first relevant result
- **Response Time**: Query execution time

## Data Sources

**Ground Truth** is derived from:
1. `scrapper/data/combined_data.json` - General places data (3,303 entries)
2. `scrapper/data/tripadvisor_da_nang_final_details.json` - Hotel-specific data (498 entries)

**Categories Available**:
- restaurant, cafe, hotel, supermarket, bar, museum, art_gallery
- bakery, campground, tourist_attraction, store, shopping_mall
- souvenir_store, clothing_store, park, zoo, amusement_park

## Usage

### Running Individual Technique Tests:
```python
from testing.comprehensive_retrieval_test import *

# Test category filtering
run_category_tests()

# Test semantic search
run_semantic_tests()

# Test location filtering
run_location_tests()

# Test distance search
run_distance_tests()

# Test combined retrieval
run_combined_tests()
```

### Running Full Evaluation:
```python
from testing.evaluation_framework import RetrievalEvaluator

evaluator = RetrievalEvaluator()
results = evaluator.run_full_evaluation()
evaluator.save_results(results)
```

## Expected Outputs

The evaluation framework generates:
1. **Console Output**: Real-time performance metrics for each query
2. **Summary Table**: Comparative performance across all techniques
3. **JSON Results**: Detailed results saved to `retrieval_evaluation_results.json`

This comprehensive testing suite enables systematic evaluation and comparison of all retrieval techniques in the system.