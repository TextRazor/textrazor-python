textrazor-python
================

Python SDK for the TextRazor Text Analytics API. 

TextRazor offers a comprehensive suite of state-of-the-art natural language processing functionality, with easy integration into your applications in minutes.  TextRazor helps hundreds of applications understand unstructured content across a range of verticals, with use cases including social media monitoring, enterprise search, recommendation systems and ad targetting.  

Read more about the TextRazor API at [https://www.textrazor.com](https://www.textrazor.com).

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
response = client.analyze_url("http://www.bbc.co.uk/news/uk-politics-18640916")

for entity in response.entities():
	print entity
```

For full API documentation visit [https://www.textrazor.com/documentation_python](https://www.textrazor.com/documentation_python).

If you have any questions please get in touch at support@textrazor.com



