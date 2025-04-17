from agents.graph import Agent

# Instantiate the agent
agent_instance = Agent()

# Get the compiled graph
graph = agent_instance.graph

# Generate the PNG visualization
# Note: This requires playwright to be installed and setup:
# pip install playwright
# playwright install
try:
    # Get the underlying graph definition
    graph_definition = graph.get_graph()
    
    # Draw the graph and save to a file
    png_data = graph_definition.draw_mermaid_png(output_file_path="workflow.png")
    print("Workflow visualization saved to workflow.png")

except ImportError as e:
    print(f"Error: Required dependency is missing. {e}")
    print("Please install playwright: pip install playwright")
    print("And install its browser dependencies: playwright install")
except Exception as e:
    print(f"An error occurred while generating the workflow visualization: {e}") 