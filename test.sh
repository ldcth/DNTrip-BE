# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Who are you?", "thread_id": "1q"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is the capital of France?", "thread_id": "1q"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is my last question?"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Who are the top 5 players in the world?"}'
curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "plan a 2 days trip to Da Nang?", "thread_id": "2kk2"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is the weather in Da Nang?", "thread_id": "c2"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi?"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "apr 19"}'

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on 25/04/2025?", "thread_id": "c212"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on 21/04/2025?"}'

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "My name is John Doe", "thread_id": "bb12"}'

# echo "Waiting for 2 seconds..."
sleep 2 # Add a pause to allow DB write to settle

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is my name?", "thread_id": "bb12"}'

