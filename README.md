TextRazor Python SDK
====================

Python SDK for the TextRazor Text Analytics API. 

TextRazor offers state-of-the-art natural language processing tools through a simple API, allowing you to build semantic technology into your applications in minutes.  

Hundreds of applications rely on TextRazor to understand unstructured text across a range of verticals, with use cases including social media monitoring, enterprise search, recommendation systems and ad targetting.  

Getting Started
===============

1. Get a free API key from [https://www.textrazor.com](https://www.textrazor.com).

2. Install the TextRazor Python SDK

```bash
pip install textrazor
```

3. Analyze your content!

```python
from textrazor import TextRazor

client = TextRazor(YOUR_API_KEY_HERE, extractors=["entities"])
response = client.analyze("Barclays misled shareholders and the public about one of the biggest investments in the bank's history, a BBC Panorama investigation has found.")

for entity in response.entities():
	print entity
```

For full API documentation visit [https://www.textrazor.com/documentation_python](https://www.textrazor.com/documentation_python).

If you have any questions please get in touch at support@textrazor.com



