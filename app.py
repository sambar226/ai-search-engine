import streamlit as st
import requests
import urllib.parse

st.set_page_config(page_title="AI Answer Engine", page_icon="🤖")
st.title("🤖 AI Answer Engine")
st.caption("Ask questions based on the crawled quotes database.")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("What did Einstein say about the world?"):
    # Add user message to chat history and display it
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response placeholder
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Safely encode the query for the URL
        encoded_query = urllib.parse.quote(prompt)
        api_url = f"http://localhost:8000/search?q={encoded_query}"
        
        try:
            # Connect to the FastAPI backend with streaming enabled
            response = requests.get(api_url, stream=True)
            response.raise_for_status()
            
            # Iterate over the Server-Sent Events (SSE) stream
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    
                    # Parse the SSE format
                    if decoded_line.startswith("data: "):
                        chunk = decoded_line[6:] # Strip out "data: "
                        
                        if chunk == "[DONE]":
                            break
                            
                        # Append the chunk and update the UI with a blinking cursor
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
            
            # Remove cursor once streaming is finished
            message_placeholder.markdown(full_response)
            
        except requests.exceptions.ConnectionError:
            full_response = "⚠️ Error: Could not connect to the backend. Is your FastAPI server running?"
            message_placeholder.error(full_response)
            
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})