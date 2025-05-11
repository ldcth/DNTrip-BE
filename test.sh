# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Who are you?", "thread_id": "1jhjqdd"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is the capital of France?", "thread_id": "1q"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is my last question?"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Who are the top 5 players in the world?"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "plan a 2 days trip to Da Nang?", "thread_id": "2kk2"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is the weather in Da Nang?", "thread_id": "c2"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi?"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "apr 19"}'

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on 25/04/2025?", "thread_id": "c212"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from Hanoi on may 12?", "thread_id": "qwe123122"}'

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "My name is John Doe", "thread_id": "bb12"}'

# echo "Waiting for 2 seconds..."
sleep 2 # Add a pause to allow DB write to settle

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "What is my name?", "thread_id": "bb12"}'

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "plan a trip to Da Nang?", "thread_id": "yu"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "for 2 days", "thread_id": "yu"}'

curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "Show me flight from hanoi to da nang", "thread_id": "nn"}'
curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "may 12", "thread_id": "nn"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "i want to book second flight", "thread_id": "cxvzvz"}'
# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "now i want to book first flight instead", "thread_id": "cxvzvz"}'

# curl -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"question": "may 10", "thread_id": "mzz"}'