# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Who are you?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "What is the capital of France?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "What is my last question?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Who are the top 5 players in the world?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "What is the weather in Da Nang?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "plan a 3 days 2 nights trip to Da Nang?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "apr 19"}'

# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on 19/04/2025?"}'
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on 22/04/2025?"}'

# # Test 1: Irrelevant query
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "What is the capital of France?"}'

# # Test 2: Multi-turn Flight Search
# # Step 2a: Ask for flights without date
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi?"}'
# # Step 2b: Provide the date (ensure this uses the same conversation context as 2a)
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "apr 19"}'

# # Test 3: Flight search for unavailable date
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on 22/04/2025?"}'

# # Test 4: Planning request
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "plan a 3 days 2 nights trip to Da Nang"}'

# # Test 5: General Da Nang question (might use QA or search)
# curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "What is the weather like in Da Nang now?"}'

# Test 6: General Da Nang question (might use QA or search)
curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "What is the weather like in Da Nang now?"}'
curl -X POST http://localhost:3001/api/travel -H "Content-Type: application/json" -d '{"question": "how about tomorrow?"}'
