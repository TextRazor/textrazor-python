"""
Copyright (c) 2023 TextRazor, https://www.textrazor.com/

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
 all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

try:
    from urllib2 import Request, urlopen, HTTPError
    from urllib import urlencode
except ImportError:
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
    from urllib.error import HTTPError

import warnings

try:
    import simplejson as json
except ImportError:
    import json

try:
    import cStringIO.StringIO as IOStream
except ImportError:
    try:
        import StringIO.StringIO as IOStream
    except ImportError:
        from io import BytesIO as IOStream

import gzip
import zlib

# These options don't usually change much within a user's app,
# for convenience allow them to set global defaults for connection options.

api_key = None
do_compression = True
do_encryption = True

# Endpoints aren't usually changed by an end user, but helpful to
# have as an option for debug purposes.

_SECURE_TEXTRAZOR_ENDPOINT = "https://api.textrazor.com/"
_TEXTRAZOR_ENDPOINT = "http://api.textrazor.com/"


def _chunks(l, n):
    n = max(1, n)
    return (l[i:i + n] for i in range(0, len(l), n))


class proxy_response_json(object):
    """ Helper class to provide a transparent proxy for python properties
    with easy access to an underlying json document. This is to avoid unneccesary
    copying of the response, while explictly exposing the expected response fields
    and documentation."""

    def __init__(self, attr_name, default=None, doc=None):
        self.attr_name = attr_name
        self.default = default

        if doc:
            self.__doc__ = doc

    def __get__(self, instance, owner=None):
        return instance.json.get(self.attr_name, self.default)

    def __set__(self, instance, value):
        instance.json[self.attr_name] = value


class proxy_member(object):
    """ Slightly redundant given the property decorator, but saves some space
    and makes non-json property access consistent with the above. """

    def __init__(self, attr_name, doc=None):
        self.attr_name = attr_name

        if doc:
            self.__doc__ = doc

    def __get__(self, instance, owner=None):
        return getattr(instance, self.attr_name)

def _generate_str(instance, banned_properties=[]):
    out = ["TextRazor", type(instance).__name__]

    try:
        out.extend(["with id:", repr(instance.id), "\n"])
    except AttributeError:
        out.extend([":\n", ])

    for prop in dir(instance):
        if not prop.startswith("_") and prop != "id" and prop not in banned_properties:
            out.extend([prop, ":", repr(getattr(instance, prop)), "\n"])

    return " ".join(out)

class TextRazorConnection(object):

    def __init__(self, local_api_key=None, local_do_compression=None, local_do_encryption=None):
        global api_key, do_compression, do_encryption, _TEXTRAZOR_ENDPOINT, _SECURE_TEXTRAZOR_ENDPOINT

        self.api_key = local_api_key
        self.do_compression = local_do_compression
        self.do_encryption = local_do_encryption

        self.endpoint = _TEXTRAZOR_ENDPOINT
        self.secure_endpoint = _SECURE_TEXTRAZOR_ENDPOINT

        if self.api_key is None:
            self.api_key = api_key
        if self.do_compression is None:
            self.do_compression = do_compression
        if self.do_encryption is None:
            self.do_encryption = do_encryption

    def set_api_key(self, api_key):
        """Sets the TextRazor API key, required for all requests."""
        self.api_key = api_key

    def set_do_compression(self, do_compression):
        """When True, request gzipped responses from TextRazor.  When expecting a large response this can
        significantly reduce bandwidth.  Defaults to True."""
        self.do_compression = do_compression

    def set_do_encryption(self, do_encryption):
        """When True, all communication to TextRazor will be sent over SSL, when handling sensitive
        or private information this should be set to True.  Defaults to False."""
        self.do_encryption = do_encryption

    def set_endpoint(self, endpoint):
        self.endpoint = endpoint

    def set_secure_endpoint(self, endpoint):
        self.secure_endpoint = endpoint

    def _build_request_headers(self, do_request_compression=False):
        request_headers = {
            'X-TextRazor-Key': self.api_key
        }

        if self.do_compression:
            request_headers['Accept-Encoding'] = 'gzip'

        if do_request_compression:
            request_headers['Content-Encoding'] = 'gzip'

        return request_headers

    def do_request(self, path, post_data=None, content_type=None, method="GET"):
        # Where compression is enabled, TextRazor supports compression of both request and response bodys.
        # Request compression can result in a significant decrease in processing time, especially for
        # larger documents.
        do_request_compression = False

        encoded_post_data = None
        if post_data:
            encoded_post_data = post_data.encode("utf-8")

            # Don't do request compression for small/empty bodies
            do_request_compression = self.do_compression and encoded_post_data and len(encoded_post_data) > 50

        request_headers = self._build_request_headers(do_request_compression)

        if content_type:
            request_headers['Content-Type'] = content_type

        if self.do_encryption:
            endpoint = self.secure_endpoint
        else:
            endpoint = self.endpoint

        url = "".join([endpoint, path])

        if do_request_compression:
            encoded_post_data = zlib.compress(encoded_post_data)

        request = Request(url, headers=request_headers, data=encoded_post_data)

        request.get_method = lambda: method

        try:
            response = urlopen(request)
        except HTTPError as e:
            raise TextRazorAnalysisException("TextRazor returned HTTP Code %d: %s" % (e.code, e.read()))

        if response.info().get('Content-Encoding') == 'gzip':
            buf = IOStream(response.read())
            response = gzip.GzipFile(fileobj=buf)

        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


class TextRazorAnalysisException(Exception):
    pass


class Topic(object):
    """Represents a single abstract topic extracted from the input text.

    Requires the "topics" extractor to be added to the TextRazor request.
    """

    def __init__(self, topic_json, link_index):
        self.json = topic_json

        for callback, arg in link_index.get(("topic", self.id), []):
            callback(arg, self)

    id = proxy_response_json("id", None, """The unique id of this Topic within the result set.""")

    label = proxy_response_json("label", None, """The label of this Topic.""")

    wikipedia_link = proxy_response_json("wikiLink", None, """A link to Wikipedia for this topic, or None if this Topic couldn't be linked to a Wikipedia page.""")

    wikidata_id = proxy_response_json("wikidataId", None, """A link to the Wikidata ID for this topic, or None if this Topic couldn't be linked to a Wikipedia page.""")

    score = proxy_response_json("score", None, """The contextual relevance of this Topic to your document.""")

    def __str__(self):
        return _generate_str(self)

    def __repr__(self):
        return "TextRazor Topic %s with label %s" % (str(self.id), str(self.label))


class Entity(object):
    """Represents a single "Named Entity" extracted from the input text.

    Requires the "entities" extractor to be added to the TextRazor request.
    """

    def __init__(self, entity_json, link_index):
        self.json = entity_json
        self._matched_words = []

        for callback, arg in link_index.get(("entity", self.document_id), []):
            callback(arg, self)

        for position in self.matched_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._matched_words.append(word)
        word._add_entity(self)

    custom_entity_id = proxy_response_json("customEntityId", "", """
    The custom entity DictionaryEntry id that matched this Entity,
    if this entity was matched in a custom dictionary.""")

    document_id = proxy_response_json("id", None)

    id = proxy_response_json("entityId", None, "The disambiguated Wikipedia ID for this entity, or None if this entity could not be disambiguated.")

    english_id = proxy_response_json("entityEnglishId", None, "The disambiguated entityId in the English Wikipedia, where a link between localized and English ID could be found. None if either the entity could not be linked, or where a language link did not exist.")

    freebase_id = proxy_response_json("freebaseId", None, "The disambiguated Freebase ID for this entity, or None if either this entity could not be disambiguated, or has no Freebase link.")

    wikidata_id = proxy_response_json("wikidataId", None, "The disambiguated Wikidata QID for this entity, or None if either this entity could not be disambiguated, or has no Freebase link.")

    wikipedia_link = proxy_response_json("wikiLink", None, "Link to Wikipedia for this entity, or None if either this entity could not be disambiguated or a Wikipedia link doesn't exist.")

    matched_text = proxy_response_json("matchedText", None, "The source text string that matched this entity")

    starting_position = proxy_response_json("startingPos", None, "The character offset in the unicode source text that marks the start of this entity.")

    ending_position = proxy_response_json("endingPos", None, "The character offset in the unicode source text that marks the end of this entity.")

    matched_positions = proxy_response_json("matchingTokens", [], "List of the token positions in the current sentence that make up this entity.")

    freebase_types = proxy_response_json("freebaseTypes", [], "List of Freebase types for this entity, or an empty list if there are none.")

    dbpedia_types = proxy_response_json("type", [], "List of Dbpedia types for this entity, or an empty list if there are none.")

    relevance_score = proxy_response_json("relevanceScore", None, """The relevance this entity has to the source text. This is a float on a scale of 0 to 1, with 1 being the most relevant.
    Relevance is computed using a number contextual clues found in the entity context and facts in the TextRazor knowledgebase.""")

    confidence_score = proxy_response_json("confidenceScore", None, """
    The confidence that TextRazor is correct that this is a valid entity. TextRazor uses an ever increasing
    number of signals to help spot valid entities, all of which contribute to this score. These include the contextual
    agreement between the words in the source text and our knowledgebase, agreement between other entities in the text,
    agreement between the expected entity type and context, and prior probabilities of having seen this entity across Wikipedia
    and other web datasets. The score ranges from 0.5 to 10, with 10 representing the highest confidence that this is
    a valid entity.""")

    data = proxy_response_json("data", {}, """Dictionary containing enriched data found for this entity.
    This is either as a result of an enrichment query, or as uploaded as part of a custom Entity Dictionary.""")

    crunchbase_id = proxy_response_json("crunchbaseId", None, "The disambiguated Crunchbase ID for this entity. None if either the entity could not be linked, or the entity was not a Company type.")

    lei = proxy_response_json("lei", None, "The disambiguated Legal Entity Identifier for this entity. None if either the entity could not be linked, or the entity was not a Company type.")

    figi = proxy_response_json("figi", None, "The disambiguated Open FIGI for this entity. None if either the entity could not be linked, or the entity was not a Company type.")

    permid = proxy_response_json("permid", None, "The disambiguated Thomson Reuters Open PermID for this entity. None if either the entity could not be linked, or the entity was not a Company type.")

    @property
    def matched_words(self):
        """Returns a list of :class:`Word` that make up this entity."""
        return self._matched_words

    def __repr__(self):
        return "TextRazor Entity %s at positions %s" % (self.id.encode("utf-8"), str(self.matched_positions))

    def __str__(self):
        return _generate_str(self)

class Entailment(object):
    """Represents a single "entailment" derived from the source text.

    Requires the "entailments" extractor to be added to the TextRazor request.
    """

    def __init__(self, entailment_json, link_index):
        self.json = entailment_json
        self._matched_words = []

        for callback, arg in link_index.get(("entailment", self.id), []):
            callback(arg, self)

        for position in self.matched_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._matched_words.append(word)
        word._add_entailment(self)

    id = proxy_response_json("id", None, "The unique id of this Entailment within the result set.")

    matched_positions = proxy_response_json("wordPositions", [], "The token positions in the current sentence that generated this entailment.")

    prior_score = proxy_response_json("priorScore", None, "The score of this entailment independent of the context it is used in this sentence.")

    context_score = proxy_response_json("contextScore", None, "Score of this entailment given the source word's usage in its sentence and the entailed word's usage in our knowledgebase")

    score = proxy_response_json("score", None, "TextRazor's overall confidence that this is a valid entailment, a combination of the prior and context score")

    @property
    def matched_words(self):
        """The :class:`Word` in the current sentence that generated this entailment."""
        return self._matched_words

    @property
    def entailed_word(self):
        """The word string that is entailed by the source words."""
        entailed_tree = self.json.get("entailedTree")
        if entailed_tree:
            return entailed_tree.get("word")

    def __repr__(self):
        return "TextRazor Entailment:\"%s\" at positions %s" % (str(self.entailed_word), str(self.matched_positions))

    def __str__(self):
        return _generate_str(self)


class RelationParam(object):
    """Represents a Param to a specific :class:`Relation`.

    Requires the "relations" extractor to be added to the TextRazor request."""

    def __init__(self, param_json, relation_parent, link_index):
        self.json = param_json
        self._relation_parent = relation_parent
        self._param_words = []

        for position in self.param_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._param_words.append(word)
        word._add_relation_param(self)

    @property
    def relation_parent(self):
        """Returns the :class:`Relation` that owns this param."""
        return self._relation_parent

    relation = proxy_response_json("relation", None, """
    The relation of this param to the predicate.
    Possible values: SUBJECT, OBJECT, OTHER""")

    param_positions = proxy_response_json("wordPositions", [], "List of the positions of the words in this param within their sentence.")

    @property
    def param_words(self):
        """Returns a list of all the :class:`Word` that make up this param."""
        return self._param_words

    def entities(self):
        """Returns a generator of all :class:`Entity` mentioned in this param."""
        seen = set()
        for word in self.param_words:
            for entity in word.entities:
                if entity not in seen:
                    seen.add(entity)
                    yield entity

    def __repr__(self):
        return "TextRazor RelationParam:\"%s\" at positions %s" % (str(self.relation), str(self.param_words))

    def __str__(self):
        return _generate_str(self)


class NounPhrase(object):
    """Represents a multi-word phrase extracted from a sentence.

    Requires the "relations" extractor to be added to the TextRazor request."""

    def __init__(self, noun_phrase_json, link_index):
        self.json = noun_phrase_json
        self._words = []

        for callback, arg in link_index.get(("nounPhrase", self.id), []):
            callback(arg, self)

        for position in self.word_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._words.append(word)
        word._add_noun_phrase(self)

    id = proxy_response_json("id", None, "The unique id of this NounPhrase within the result set.")

    word_positions = proxy_response_json("wordPositions", None, "List of the positions of the words in this phrase.")

    @property
    def words(self):
        """Returns a list of :class:`Word` that make up this phrase."""
        return self._words

    def __repr__(self):
        return "TextRazor NounPhrase at positions %s" % (str(self.words))

    def __str__(self):
        return _generate_str(self, banned_properties=["word_positions", ])

class Property(object):
    """Represents a property relation extracted from raw text.  A property implies an "is-a" or "has-a" relationship
    between the predicate (or focus) and its property.

    Requires the "relations" extractor to be added to the TextRazor request.
    """

    def __init__(self, property_json, link_index):
        self.json = property_json
        self._predicate_words = []
        self._property_words = []

        for callback, arg in link_index.get(("property", self.id), []):
            callback(arg, self)

        for position in self.predicate_positions:
            try:
                link_index[("word", position)].append((self._register_link, True))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, True)]

        for position in self.property_positions:
            try:
                link_index[("word", position)].append((self._register_link, False))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, False)]

    def _register_link(self, is_predicate, word):
        if is_predicate:
            self._predicate_words.append(word)
            word._add_property_predicate(self)
        else:
            self._property_words.append(word)
            word._add_property_properties(self)

    id = proxy_response_json("id", None, "The unique id of this NounPhrase within the result set.")

    predicate_positions = proxy_response_json("wordPositions", [], "List of the positions of the words in the predicate (or focus) of this property.")

    predicate_words = proxy_member("_predicate_words", "List of TextRazor words that make up the predicate (or focus) of this property.")

    property_positions = proxy_response_json("propertyPositions", [], "List of the positions of the words that modify the predicate of this property.")

    property_words = proxy_member("_property_words", "List of :class:`Word` that modify the predicate of this property.")

    def __repr__(self):
        return "TextRazor Property at positions %s" % (str(self.predicate_positions))

    def __str__(self):
        return _generate_str(self, banned_properties=["predicate_positions", ])

class Relation(object):
    """Represents a grammatical relation between words.  Typically owns a number of
    :class:`RelationParam`, representing the SUBJECT and OBJECT of the relation.

    Requires the "relations" extractor to be added to the TextRazor request."""

    def __init__(self, relation_json, link_index):
        self.json = relation_json

        self._params = [RelationParam(param, self, link_index) for param in relation_json["params"]]
        self._predicate_words = []

        for callback, arg in link_index.get(("relation", self.id), []):
            callback(arg, self)

        for position in self.predicate_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._predicate_words.append(word)
        word._add_relation(self)

    id = proxy_response_json("id", None, "The unique id of this Relation within the result set.")

    predicate_positions = proxy_response_json("wordPositions", [], "List of the positions of the predicate words in this relation.")

    predicate_words = proxy_member("_predicate_words", "List of the positions of the predicate words in this relation.")

    params = proxy_member("_params", "List of the TextRazor RelationParam that are part of this relation.")

    def __repr__(self):
        return "TextRazor Relation at positions %s" % (str(self.predicate_words))

    def __str__(self):
        return _generate_str(self, banned_properties=["predicate_positions", ])

class Word(object):
    """Represents a single Word (token) extracted by TextRazor.

    Requires the "words" extractor to be added to the TextRazor request."""

    def __init__(self, response_word, link_index):
        self.json = response_word

        self._parent = None
        self._children = []

        self._entities = []
        self._entailments = []
        self._relations = []
        self._relation_params = []
        self._property_predicates = []
        self._property_properties = []
        self._noun_phrases = []

        for callback, arg in link_index.get(("word", self.position), []):
            callback(arg, self)

    def _add_child(self, child):
        self._children.append(child)

    def _set_parent(self, parent):
        self._parent = parent
        parent._add_child(self)

    def _add_entity(self, entity):
        self._entities.append(entity)

    def _add_entailment(self, entailment):
        self._entailments.append(entailment)

    def _add_relation(self, relation):
        self._relations.append(relation)

    def _add_relation_param(self, relation_param):
        self._relation_params.append(relation_param)

    def _add_property_predicate(self, property):
        self._property_predicates.append(property)

    def _add_property_properties(self, property):
        self._property_properties.append(property)

    def _add_noun_phrase(self, noun_phrase):
        self._noun_phrases.append(noun_phrase)

    parent_position = proxy_response_json("parentPosition", None, """
    The position of the grammatical parent of this Word, or None if this Word is either at the root
    of the sentence or the "dependency-trees" extractor was not requested.""")

    parent = proxy_member("_parent", """
    Link to the TextRazor Word that is parent of this Word, or None if this word is either at the root
    of the sentence or the "dependency-trees" extractor was not requested.""")

    relation_to_parent = proxy_response_json("relationToParent", None, """
    Returns the grammatical relation between this word and its parent, or None if this Word is either at the root
    of the sentence or the "dependency-trees" extractor was not requested.

    TextRazor parses into the Stanford uncollapsed dependencies, as detailed at:

    http://nlp.stanford.edu/software/dependencies_manual.pdf""")

    children = proxy_member("_children", """
    List of TextRazor words that make up the children of this word.  Returns an empty list
    for leaf words, or if the "dependency-trees" extractor was not requested.""")

    position = proxy_response_json("position", None, "The position of this word in its sentence.")

    stem = proxy_response_json("stem", None, "The stem of this word.")

    lemma = proxy_response_json("lemma", None, "The morphological root of this word, see http://en.wikipedia.org/wiki/Lemma_(morphology) for details.")

    token = proxy_response_json("token", None, "The raw token string that matched this word in the source text.")

    part_of_speech = proxy_response_json("partOfSpeech", None, """
    The Part of Speech that applies to this word. We use the Penn treebank tagset,
    as detailed here:

    http://www.comp.leeds.ac.uk/ccalas/tagsets/upenn.html""")

    input_start_offset = proxy_response_json("startingPos", None, """
    The start offset in the input text for this token. Note that this offset applies to the
    original Unicode string passed in to the api, TextRazor treats multi byte utf8 charaters as a single position.""")

    input_end_offset = proxy_response_json("endingPos", None, """
    The end offset in the input text for this token. Note that this offset applies to the
    original Unicode string passed in to the api, TextRazor treats multi byte utf8 charaters as a single position.""")

    entailments = proxy_member("_entailments", "List of :class:`Entailment` that this word entails")

    entities = proxy_member("_entities", "List of :class:`Entity` that this word is a part of.")

    relations = proxy_member("_relations", "List of :class:`Relation` that this word is a predicate of.")

    relation_params = proxy_member("_relation_params", "List of :class:`RelationParam` that this word is a member of.")

    property_properties = proxy_member("_property_properties", "List of :class:`Property` that this word is a property member of.")

    property_predicates = proxy_member("_property_predicates", "List of :class:`Property` that this word is a predicate (or focus) member of.")

    noun_phrases = proxy_member("_noun_phrases", "List of :class:`NounPhrase` that this word is a member of.")

    senses = proxy_response_json("senses", [], "List of {'sense', 'score'} dictionaries representing scores of each Wordnet sense this this word may be a part of.")

    spelling_suggestions = proxy_response_json("spellingSuggestions", [], "List of {'suggestion', 'score'} dictionaries representing scores of each spelling suggestion that might replace this word. This property requires the \"spelling\" extractor to be sent with your request.")

    def __repr__(self):
        return "TextRazor Word:\"%s\" at position %s" % ((self.token).encode("utf-8"), str(self.position))

    def __str__(self):
        return _generate_str(self)

class Sentence(object):
    """Represents a single sentence extracted by TextRazor."""

    def __init__(self, sentence_json, link_index):
        if "words" in sentence_json:
            self._words = [Word(word_json, link_index) for word_json in sentence_json["words"]]
        else:
            self._words = []

        self._add_links(link_index)

    def _add_links(self, link_index):
        if not self._words:
            return

        self._root_word = None

        # Add links between the parent/children of the dependency tree in this sentence.

        word_positions = {}
        for word in self._words:
            word_positions[word.position] = word

        for word in self._words:
            parent_position = word.parent_position
            if parent_position is not None and parent_position >= 0:
                word._set_parent(word_positions[parent_position])
            elif word.part_of_speech not in ("$", "``", "''", "(", ")", ",", "--", ".", ":"):
                # Punctuation does not get attached to any parent, any non punctuation part of speech
                # must be the root word.
                self._root_word = word

    root_word = proxy_member("_root_word", """The root word of this sentence if "dependency-trees" extractor was requested""")

    words = proxy_member("_words", """List of all the :class:`Word` in this sentence""")


class CustomAnnotation(object):

    def __init__(self, annotation_json, link_index):
        self.json = annotation_json

        for key_value in annotation_json.get("contents", []):
            for link in key_value.get("links", []):
                try:
                    link_index[(link["annotationName"], link["linkedId"])].append((self._register_link, link))
                except Exception:
                    link_index[(link["annotationName"], link["linkedId"])] = [(self._register_link, link)]

    def _register_link(self, link, annotation):
        link["linked"] = annotation

        new_custom_annotation_list = []
        try:
            new_custom_annotation_list = getattr(annotation, self.name())
        except Exception:
            pass
        new_custom_annotation_list.append(self)
        setattr(annotation, self.name(), new_custom_annotation_list)

    def name(self):
        return self.json["name"]

    def __getattr__(self, attr):
        exists = False
        for key_value in self.json["contents"]:
            if "key" in key_value and key_value["key"] == attr:
                exists = True
                for link in key_value.get("links", []):
                    try:
                        yield link["linked"]
                    except Exception:
                        yield link
                for int_value in key_value.get("intValue", []):
                    yield int_value
                for float_value in key_value.get("floatValue", []):
                    yield float_value
                for str_value in key_value.get("stringValue", []):
                    yield str_value
                for bytes_value in key_value.get("bytesValue", []):
                    yield bytes_value

        if not exists:
            raise AttributeError("%r annotation has no attribute %r" % (self.name(), attr))

    def __repr__(self):
        return "TextRazor CustomAnnotation:\"%s\"" % (self.json["name"])

    def __str__(self):
        out = ["TextRazor CustomAnnotation:", str(self.json["name"]), "\n"]

        for key_value in self.json["contents"]:
            try:
                out.append("Param %s:" % key_value["key"])
            except Exception:
                out.append("Param (unlabelled):")
            out.append("\n")
            for link in self.__getattr__(key_value["key"]):
                out.append(repr(link))
                out.append("\n")

        return " ".join(out)


class TextRazorResponse(object):
    """Represents a processed response from TextRazor."""

    def __init__(self, response_json):
        self.json = response_json

        self._sentences = []
        self._custom_annotations = []
        self._topics = []
        self._coarse_topics = []
        self._entities = []
        self._entailments = []
        self._relations = []
        self._properties = []
        self._noun_phrases = []
        self._categories = []

        link_index = {}

        if "response" in self.json:
            # There's a bit of magic here.  Each annotation registers a callback with the ids and types of annotation
            # that it is linked to.  When the linked annotation is later parsed it adds the link via the callback.
            # This means that annotations must be added in order of the dependency between them.

            if "customAnnotations" in self.json["response"]:
                self._custom_annotations = [CustomAnnotation(json, link_index) for json in self.json["response"]["customAnnotations"]]

            if "topics" in self.json["response"]:
                self._topics = [Topic(topic_json, link_index) for topic_json in self.json["response"]["topics"]]

            if "coarseTopics" in self.json["response"]:
                self._coarse_topics = [Topic(topic_json, link_index) for topic_json in self.json["response"]["coarseTopics"]]

            if "entities" in self.json["response"]:
                self._entities = [Entity(entity_json, link_index) for entity_json in self.json["response"]["entities"]]

            if "entailments" in self.json["response"]:
                self._entailments = [Entailment(entailment_json, link_index) for entailment_json in self.json["response"]["entailments"]]

            if "relations" in self.json["response"]:
                self._relations = [Relation(relation_json, link_index) for relation_json in self.json["response"]["relations"]]

            if "properties" in self.json["response"]:
                self._properties = [Property(property_json, link_index) for property_json in self.json["response"]["properties"]]

            if "nounPhrases" in self.json["response"]:
                self._noun_phrases = [NounPhrase(phrase_json, link_index) for phrase_json in self.json["response"]["nounPhrases"]]

            if "sentences" in self.json["response"]:
                self._sentences = [Sentence(sentence_json, link_index) for sentence_json in self.json["response"]["sentences"]]

            if "categories" in self.json["response"]:
                self._categories = [ScoredCategory(category_json) for category_json in self.json["response"]["categories"]]

    @property
    def raw_text(self):
        """"When the set_cleanup_return_raw option is enabled, contains the input text before any cleanup."""
        return self.json["response"].get("rawText", "")

    @property
    def cleaned_text(self):
        """"When the set_cleanup_return_cleaned option is enabled, contains the input text after any cleanup/article extraction."""
        return self.json["response"].get("cleanedText", "")

    @property
    def language(self):
        """"The ISO-639-2 language used to analyze this document, either explicitly provided as the languageOverride, or as detected by the language detector."""
        return self.json["response"].get("language", "")

    @property
    def custom_annotation_output(self):
        """"Any output generated while running the embedded Prolog engine on your rules."""
        return self.json["response"].get("customAnnotationOutput", "")

    ok = proxy_response_json("ok", False, """
    True if TextRazor successfully analyzed your document, False if there was some error.
    More detailed information about the error is available in the :meth:`error` property.
    """)

    error = proxy_response_json("error", "", """
    Descriptive error message of any problems that may have occurred during analysis,
    or an empty string if there was no error.
    """)

    message = proxy_response_json("message", "", """
    Any warning or informational messages returned from the server.
    """)

    def coarse_topics(self):
        """Returns a list of all the coarse :class:`Topic` in the response. """
        return self._coarse_topics

    def topics(self):
        """Returns a list of all the :class:`Topic` in the response. """
        return self._topics

    def entities(self):
        """Returns a list of all the :class:`Entity` across all sentences in the response."""
        return self._entities

    def words(self):
        """Returns a generator of all :class:`Word` across all sentences in the response."""
        for sentence in self._sentences:
            for word in sentence.words:
                yield word

    def entailments(self):
        """Returns a list of all :class:`Entailment` across all sentences in the response."""
        return self._entailments

    def relations(self):
        """Returns a list of all :class:`Relation` across all sentences in the response."""
        return self._relations

    def properties(self):
        """Returns a list of all :class:`Property` across all sentences in the response."""
        return self._properties

    def noun_phrases(self):
        """Returns a list of all the :class:`NounPhrase` across all sentences in the response."""
        return self._noun_phrases

    def sentences(self):
        """Returns a list of all :class:`Sentence` in the response."""
        return self._sentences

    def categories(self):
        """List of all :class:`ScoredCategory` in the response."""
        return self._categories

    def matching_rules(self):
        """Returns a list of rule names that matched this document."""
        return [custom_annotation.name() for custom_annotation in self._custom_annotations]

    def summary(self):
        return """Request processed in: %s seconds.  Num Sentences:%s""" % (
            self.json["time"], len(self.json["response"]["sentences"])
        )

    def __getattr__(self, attr):
        exists = False
        for custom_annotation in self._custom_annotations:
            if custom_annotation.name() == attr:
                exists = True
                yield custom_annotation

        if not exists:
            raise AttributeError("TextRazor response has no annotation %r" % attr)


class AllDictionaryEntriesResponse(object):

    def __init__(self, json):
        self.json = json

        self.entries = [DictionaryEntry(dictionary_json) for dictionary_json in json.get("entries", [])]

    total = proxy_response_json("total", 0, """
    The total number of DictionaryEntry in this Dictionary.
    """)

    limit = proxy_response_json("limit", 0, """
    The maximium number of DictionaryEntry to be returned.
    """)

    offset = proxy_response_json("offset", 0, """
    Offset into the full list of DictionaryEntry that this result set started from.
    """)


class DictionaryManager(TextRazorConnection):

    path = "entities/"

    def __init__(self, api_key=None):
        super(DictionaryManager, self).__init__(api_key)

    def create_dictionary(self, dictionary_properties):
        """ Creates a new dictionary using properties provided in the dict dictionary_properties.
        See the properties of class Dictionary for valid options.

        >>> import textrazor
        >>> dictionary_manager = textrazor.DictionaryManager("YOUR_API_KEY_HERE")
        >>>
        >>> dictionary_manager.create_dictionary({"id":"UNIQUE_ID"})
        """

        new_dictionary = Dictionary({})

        for key, value in dictionary_properties.items():
            if not hasattr(new_dictionary, key):
                valid_options = ",".join(name for name, obj in Dictionary.__dict__.items() if isinstance(obj, proxy_response_json))

                raise TextRazorAnalysisException("Cannot create dictionary, unexpected param: %s. Supported params: %s" % (key, valid_options))

            setattr(new_dictionary, key, value)

        # Check for the existence of a dictionary ID, without that
        # we can't generate a URL and the server will return an unhelpful message.
        if not new_dictionary.id:
            raise TextRazorAnalysisException("Cannot create dictionary, dictionary id not provided.")

        dictionary_path = "".join([self.path, new_dictionary.id])

        self.do_request(dictionary_path, json.dumps(new_dictionary.json), method="PUT")

        # The server may have added some optional fields so we want to force the user to "get" the new dictionary.
        return self.get_dictionary(new_dictionary.id)

    def all_dictionaries(self):
        """ Returns a list of all Dictionary in your account.

        >>> for dictionary in dictionary_manager.all_dictionaries():
        >>>     print dictionary.id
        """

        response = self.do_request(self.path)

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve all dictionaries. Error: %s" % str(response))

        if "dictionaries" in response:
            return [Dictionary(dictionary_json) for dictionary_json in response["dictionaries"]]

        return []

    def get_dictionary(self, id):
        """ Returns a Dictionary object by id.

        >>> print dictionary_manager.get_id("UNIQUE_ID").language
        """
        dictionary_path = "".join([self.path, id])
        response = self.do_request(dictionary_path, method="GET")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve dictionary with id: %s. Error: %s" % (id, str(response)))

        return Dictionary(response["response"])

    def delete_dictionary(self, id):
        """ Deletes a dictionary and all its entries by id.

        >>> dictionary_manager.delete_dictionary("UNIQUE_ID")
        """
        dictionary_path = "".join([self.path, id])
        response = self.do_request(dictionary_path, method="DELETE")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("Unable to delete dictionary with ID:%s. Error: %s" % (id, str(response)))

    def all_entries(self, dictionary_id, limit=None, offset=None):
        """ Returns a AllDictionaryEntriesResponse containing all DictionaryEntry for dictionary with id dictionary_id, along with paging information.

        Larger dictionaries can be too large to download all at once. Where possible it is recommended that you use
        limit and offset paramaters to control the TextRazor response, rather than filtering client side.

        >>> entry_response = dictionary_manager.all_entries("UNIQUE_ID", limit=10, offset=10)
        >>> for entry in entry_response.entries:
        >>>     print entry.text
        """

        params = {}
        if limit:
            params['limit'] = limit
        if offset:
            params['offset'] = offset

        all_path = "".join([self.path, dictionary_id, "/_all?", urlencode(params)])

        response = self.do_request(all_path, method="GET")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve dictionary entries with dictionary id: %s, Error: %s" % (dictionary_id, str(response)))

        return AllDictionaryEntriesResponse(response["response"])

    def add_entries(self, dictionary_id, entities):
        """ Adds entries to a dictionary with id dictionary_id.

        Entries must be a List of dicts corresponding to properties of the new DictionaryEntry objects.
        At a minimum this would be [{'text':'test text to match'}].

        >>> dictionary_manager.add_entries("UNIQUE_ID", [{'text':'test text to match'}, {'text':'more text to match', 'id':'UNIQUE_ENTRY_ID'}])
        """
        dictionary_path = "".join([self.path, dictionary_id, "/"])
        all_entries = []

        for entity in entities:
            new_entry = DictionaryEntry({})

            for key, value in entity.items():
                if not hasattr(new_entry, key):
                    valid_options = ",".join(name for name, obj in DictionaryEntry.__dict__.items() if isinstance(obj, proxy_response_json))

                    raise TextRazorAnalysisException("Cannot create dictionary entry, unexpected param: %s. Supported params: %s" % (key, valid_options))

                setattr(new_entry, key, value)

            all_entries.append(new_entry.json)

        # For performance reasons TextRazor expects a maximum of 20000 dictionary entries at a time,
        # we transparently batch them up here.

        for batch in _chunks(all_entries, 20000):
            response = self.do_request(dictionary_path, json.dumps(batch), method="POST")

            if "ok" in response and not response["ok"]:
                raise TextRazorAnalysisException("Unable to add entries to dictionary with ID:%s. Error: %s" % (dictionary_id, str(response)))

    def delete_entry(self, dictionary_id, entry_id):
        """Deletes a specific DictionaryEntry by dictionary id and entry id.

        For performance reasons it's always faster to perform major changes
        to dictionaries by deleting and recreating the whole dictionary rather than removing
        many individual entries.

        >>> dictionary_manager.delete_entry('UNIQUE_ID', 'UNIQUE_ENTRY_ID')
        """

        dictionary_path = "".join([self.path, dictionary_id, "/", entry_id])

        response = self.do_request(dictionary_path, method="DELETE")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to delete dictionary entry with dictionary id: %s, entry id: %s Error: %s" % (dictionary_id, entry_id, str(response)))

    def get_entry(self, dictionary_id, entry_id):
        """ Retrieves a specific DictionaryEntry by dictionary id and entry id.

        >>> print dictionary_manager.get_id('UNIQUE_ID', 'UNIQUE_ENTRY_ID').text
        """

        dictionary_path = "".join([self.path, dictionary_id, "/", entry_id])

        response = self.do_request(dictionary_path, method="GET")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve dictionary entry with dictionary id: %s, entry id: %s Error: %s" % (dictionary_id, entry_id, str(response)))

        return DictionaryEntry(response["response"])


class DictionaryEntry(object):

    def __init__(self, json):
        self.json = json

    id = proxy_response_json("id", "", """
    Unique ID for this entry, used to identify and manipulate specific entries.

    Defaults to an automatically generated unique id.
    """)

    text = proxy_response_json("text", "", """
    Unicode string representing the text to match to this DictionaryEntry.
    """)

    data = proxy_response_json("data", {}, """
    A dictionary mapping string keys to lists of string data values.
    TextRazor will return this dictionary to you as part of the Entity 'data' property whenever it matches this entry.
    This is useful for adding application-specific metadata to each entry.

    >>> {'type':['people', 'person', 'politician']}
    """)


class Dictionary(object):

    def __init__(self, json):
        self.json = json

    match_type = proxy_response_json("matchType", "", """
    Controls any pre-processing done on your dictionary before matching.

    Valid options are:
    stem    - Words are split and "stemmed" before matching, resulting in a more relaxed match.
              This is an easy way to match plurals - love, loved, loves will all match the same dictionary entry.
              This implicitly sets "case_insensitive" to True.

    token   - Words are split and matched literally.

    Defaults to 'token'.""")

    case_insensitive = proxy_response_json("caseInsensitive", False, """
    When True, this dictionary will match both uppercase and lowercase characters.
    """)

    id = proxy_response_json("id", "", """
    The unique identifier for this dictionary.
    """)

    language = proxy_response_json("language", "", """
    When set to a ISO-639-2 language code, this dictionary will only match documents of the corresponding language.

    When set to 'any', this dictionary will match any document.

    Defaults to 'any'.
    """)


class AllCategoriesResponse(object):

    def __init__(self, json):
        self.json = json
        self.categories = [Category(category_json) for category_json in json.get("categories", [])]

    total = proxy_response_json("total", 0, """
    The total number of Category in this Classifier.
    """)

    limit = proxy_response_json("limit", 0, """
    The maximium number of Category to be returned.
    """)

    offset = proxy_response_json("offset", 0, """
    Offset into the full list of Category that this result set started from.
    """)


class ScoredCategory(object):

    def __init__(self, json):
        self.json = json

    classifier_id = proxy_response_json("classifierId", "", """
    The unique identifier for the classifier that matched this ScoredCategory.
    """)

    category_id = proxy_response_json("categoryId", "", """
    The unique identifier of this category.
    """)

    label = proxy_response_json("label", "", """
    The human readable label for this category.
    """)

    score = proxy_response_json("score", 0, """
    The score TextRazor has assigned to this category, between 0 and 1.
    """)


class Category(object):
    path = "categories/"

    def __init__(self, json):
        self.json = json

    query = proxy_response_json("query", "", """The query used to define this category.""")

    category_id = proxy_response_json("categoryId", "", """The unique ID for this category within its classifier.""")

    label = proxy_response_json("label", "", """The human readable label for this category. This is an optional field.""")


class ClassifierManager(TextRazorConnection):

    path = "categories/"

    def __init__(self, api_key=None):
        super(ClassifierManager, self).__init__(api_key)

    def delete_classifier(self, classifier_id):
        """ Deletes a Classifier and all its Categories by id. """
        classifier_path = "".join([self.path, classifier_id])
        self.do_request(classifier_path, method="DELETE")

    def create_classifier(self, classifier_id, categories):
        """ Creates a new classifier using the provided list of Category.

        See the properties of class Category for valid options. """

        classifier_path = "".join([self.path, classifier_id])

        all_categories = []

        for category in categories:
            new_category = Category({})

            for key, value in category.items():
                if not hasattr(new_category, key):
                    valid_options = ",".join(name for name, obj in Category.__dict__.items() if isinstance(obj, proxy_response_json))

                    raise TextRazorAnalysisException("Cannot create category, unexpected param: %s. Supported params: %s" % (key, valid_options))

                setattr(new_category, key, value)

            all_categories.append(new_category.json)

        self.do_request(classifier_path, json.dumps(all_categories), content_type="application/json", method="PUT")

    def create_classifier_with_csv(self, classifier_id, categories_csv):
        """ Uploads the string contents of a CSV file containing new categories to be added to the classifier called classifier_name.
           Any existing classifier with this ID will be replaced. """

        classifier_path = "".join([self.path, classifier_id])
        self.do_request(classifier_path, categories_csv, content_type="application/csv", method="PUT")

    def all_categories(self, classifier_id, limit=None, offset=None):
        """ Returns a AllCategoriesResponse containing all Categories for classifier with id classifier_id, along with paging information.

        Larger classifiers can be too large to download all at once. Where possible it is recommended that you use
        limit and offset paramaters to control the TextRazor response, rather than filtering client side.

        >>> category_response = classifier_manager.all_entries("UNIQUE_CLASSIFIER_ID", limit=10, offset=10)
        >>> for category in category_response.categories:
        >>>     print category.text
        """

        params = {}
        if limit:
            params['limit'] = limit
        if offset:
            params['offset'] = offset

        all_path = "".join([self.path, classifier_id, "/_all?", urlencode(params)])

        response = self.do_request(all_path, method="GET")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve categories for classifier id: %s, Error: %s" % (classifier_id, str(response)))

        return AllCategoriesResponse(response["response"])

    def delete_category(self, classifier_id, category_id):
        """ Deletes a Category by ID. """
        category_path = "".join([self.path, classifier_id, "/", category_id])
        self.do_request(category_path, method="DELETE")

    def get_category(self, classifier_id, category_id):
        """ Returns a Category by ID. """
        category_path = "".join([self.path, classifier_id, "/", category_id])

        response = self.do_request(category_path, method="GET")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve category for classifier id: %s, Error: %s" % (classifier_id, str(response)))

        return Category(response["response"])

class Account(object):

    def __init__(self, json):
        self.json = json

    plan = proxy_response_json("plan", "", """
    The ID of your current subscription plan.
    """)

    concurrent_request_limit = proxy_response_json("concurrentRequestLimit", 0, """
    The maximum number of requests your account can make at the same time.
    """)

    concurrent_requests_used = proxy_response_json("concurrentRequestsUsed", 0, """
    The number of requests currently being processed by your account.
    """)

    plan_daily_included_requests = proxy_response_json("planDailyRequestsIncluded", 0, """
    The daily number of requests included with your subscription plan.
    """)

    requests_used_today = proxy_response_json("requestsUsedToday", 0, """
    The total number of requests that have been made today.
    """)

class AccountManager(TextRazorConnection):

    path = "account/"

    def __init__(self, api_key=None):
        super(AccountManager, self).__init__(api_key)

    def get_account(self):
        """ Retrieves the Account settings and realtime usage statistics for your account.

        This call does not count towards your daily request or concurrency limits.

        >>> import textrazor
        >>> textrazor.api_key = "YOUR_API_KEY_HERE"
        >>>
        >>> account_manager = textrazor.AccountManager()
        >>>
        >>> print account_manager.get_account().requests_used_today
        """

        response = self.do_request(self.path, method="GET")

        if "ok" in response and not response["ok"]:
            raise TextRazorAnalysisException("TextRazor was unable to retrieve your account details, Error: %s" % str(response))

        return Account(response["response"])


class TextRazor(TextRazorConnection):
    """
    The main TextRazor client.  To process your text, create a :class:`TextRazor` instance with your API key
    and set the extractors you need to process the text.  Calls to :meth:`analyze` and :meth:`analyze_url` will then process raw text or URLs
    , returning a :class:`TextRazorResponse` on success.

    This class is threadsafe once initialized with the request options.  You should create a new instance for each request
    if you are likely to be changing the request options in a multithreaded environment.

    Below is an entity extraction example from the tutorial, you can find more examples at http://www.textrazor.com/tutorials.

    >>> import textrazor
    >>>
    >>> client = textrazor.TextRazor("API_KEY_GOES_HERE", extractors=["entities"])
    >>> client.set_cleanup_mode("cleanHTML")
    >>>
    >>> response = client.analyze_url("http://www.bbc.co.uk/news/uk-politics-18640916")
    >>>
    >>> entities = list(response.entities())
    >>> entities.sort(key=lambda x: x.relevance_score, reverse=True)
    >>>
    >>> seen = set()
    >>> for entity in entities:
    >>>     if entity.id not in seen:
    >>>         print entity.id, entity.relevance_score, entity.confidence_score, entity.freebase_types
    >>>         seen.add(entity.id)
    """

    def __init__(self, api_key=None, extractors=[], do_compression=None, do_encryption=None):
        super(TextRazor, self).__init__(api_key, do_compression, do_encryption)

        self.extractors = extractors
        self.cleanup_html = False
        self.cleanup_mode = None
        self.cleanup_return_cleaned = None
        self.cleanup_return_raw = None
        self.cleanup_use_metadata = None
        self.download_user_agent = None
        self.rules = ""
        self.language_override = None
        self.enrichment_queries = []
        self.dbpedia_type_filters = []
        self.freebase_type_filters = []
        self.allow_overlap = None
        self.entity_dictionaries = []
        self.classifiers = []
        self.classifier_max_categories = None

    def set_extractors(self, extractors):
        """Sets a list of "Extractors" which extract various information from your text.
        Only select the extractors that are explicitly required by your application for optimal performance.
        Any extractor that doesn't match one of the predefined list below will be assumed to be a custom Prolog extractor.

        Valid options are: words, phrases, entities, dependency-trees, relations, entailments. """
        self.extractors = extractors

    def set_rules(self, rules):
        """Sets a string containing Prolog logic.  All rules matching an extractor name listed in the request will be evaluated
        and all matching param combinations linked in the response. """
        self.rules = rules

    def set_enrichment_queries(self, enrichment_queries):
        """Set a list of "Enrichment Queries", used to enrich the entity response with structured linked data.
        The syntax for these queries is documented at https://www.textrazor.com/enrichment """
        self.enrichment_queries = enrichment_queries

    def set_language_override(self, language_override):
        """When set to a ISO-639-2 language code, force TextRazor to analyze content with this language.
        If not set TextRazor will use the automatically identified language.
        """
        self.language_override = language_override

    def set_do_cleanup_HTML(self, cleanup_html):
        """When True, input text is treated as raw HTML and will be cleaned of tags, comments, scripts,
        and boilerplate content removed.  When this option is enabled, the cleaned_text property is returned
        with the text content, providing access to the raw filtered text.  When enabled, position offsets returned
        in individual words apply to the clean text, not the provided HTML."""

        warnings.warn("set_do_cleanup_HTML has been deprecated. Please see set_cleanup_mode for a more flexible cleanup option.", DeprecationWarning)

        self.cleanup_html = cleanup_html

    def set_cleanup_mode(self, cleanup_mode):
        """Controls the preprocessing cleanup mode that TextRazor will apply to your content before analysis.
        For all options aside from "raw" any position offsets returned will apply to the final cleaned text,
        not the raw HTML. If the cleaned text is required please see the :meth:`set_cleanup_return_cleaned' option.

        Valid options are:
        raw       - Content is analyzed "as-is", with no preprocessing.
        cleanHTML - Boilerplate HTML is removed prior to analysis, including tags, comments, menus, leaving only the
                    body of the article.
        stripTags - All Tags are removed from the document prior to analysis. This will remove all HTML, XML tags, but
                    the content of headings, menus will remain. This is a good option for analysis of HTML pages that aren't
                    long form documents.

        Defaults to "raw" for analyze requests, and "cleanHTML" for analyze_url requests.
        """
        self.cleanup_mode = cleanup_mode

    def set_cleanup_return_cleaned(self, return_cleaned):
        """When return_cleaned is True, the TextRazor response will contain the cleaned_text property. To save bandwidth, only set this to
        True if you need it in your application. Defaults to False."""
        self.cleanup_return_cleaned = return_cleaned

    def set_cleanup_return_raw(self, return_raw):
        """When return_raw is True, the TextRazor response will contain the raw_text property, the original text TextRazor received or downloaded
        before cleaning. To save bandwidth, only set this to True if you need it in your application. Defaults to False."""
        self.cleanup_return_raw = return_raw

    def set_cleanup_use_metadata(self, use_metadata):
        """When use_metadata is True, TextRazor will use metadata extracted from your document to help in the disambiguation/extraction
        process. This include HTML titles and metadata, and can significantly improve results for shorter documents without much other
        content.

        This option has no effect when cleanup_mode is 'raw'.
        """
        self.cleanup_use_metadata = use_metadata

    def set_download_user_agent(self, user_agent):
        """Sets the User-Agent header to be used when downloading URLs through analyze_url. This should be a descriptive string identifying
        your application, or an end user's browser user agent if you are performing live requests from a given user.

        Defaults to "TextRazor Downloader (https://www.textrazor.com)"
        """
        self.download_user_agent = user_agent

    def set_entity_dictionaries(self, entity_dictionaries):
        """Sets a list of the custom entity dictionaries to match against your content. Each item should be a string ID
        corresponding to dictionaries you have previously configured through the textrazor.Dictionary interface."""
        self.entity_dictionaries = entity_dictionaries

    def set_entity_allow_overlap(self, allow_overlap):
        """When allow_overlap is True, entities in the response may overlap. When False, the "best" entity
        is found such that none overlap. Defaults to True. """
        self.allow_overlap = allow_overlap

    def set_entity_dbpedia_type_filters(self, filters):
        """Set a list of DBPedia types to filter entity extraction on. All returned entities must
        match at least one of these types."""
        self.dbpedia_type_filters = filters

    def set_entity_freebase_type_filters(self, filters):
        """Set a list of Freebase types to filter entity extraction on. All returned entities must
        match at least one of these types."""
        self.freebase_type_filters = filters

    def set_classifiers(self, classifiers):
        """Sets a list of classifiers to evaluate against your document. Each entry should be a string ID corresponding to either one of TextRazor's default classifiers, or one you have previously configured through the ClassifierManager interface.

        Valid Options are:
        textrazor_iab Score against the Internet Advertising Bureau QAG segments - approximately 400 high level categories arranged into two tiers.
        textrazor_newscodes Score against the IPTC newscodes - approximately 1400 high level categories organized into a three level tree.
        custom classifier name Score against a custom classifier, previously created through the Classifier Manager interface."""
        self.classifiers = classifiers

    def set_classifier_max_categories(self, max_categories):
        """Sets the maximum number of matching categories to retrieve from the TextRazor."""
        self.classifier_max_categories = max_categories

    def _add_optional_param(self, post_data, param, value):
        if value is not None:
            post_data.append((param, value))

    def _build_post_data(self):
        post_data = [("rules", self.rules),
                     ("extractors", ",".join(self.extractors)),
                     ("cleanupHTML", self.cleanup_html),
                     ("classifiers", ",".join(self.classifiers))]

        for dictionary in self.entity_dictionaries:
            post_data.append(("entities.dictionaries", dictionary))

        for filter in self.dbpedia_type_filters:
            post_data.append(("entities.filterDbpediaTypes", filter))

        for filter in self.freebase_type_filters:
            post_data.append(("entities.filterFreebaseTypes", filter))

        for query in self.enrichment_queries:
            post_data.append(("entities.enrichmentQueries", query))

        self._add_optional_param(post_data, "entities.allowOverlap", self.allow_overlap)
        self._add_optional_param(post_data, "languageOverride", self.language_override)
        self._add_optional_param(post_data, "cleanup.mode", self.cleanup_mode)
        self._add_optional_param(post_data, "cleanup.returnCleaned", self.cleanup_return_cleaned)
        self._add_optional_param(post_data, "cleanup.returnRaw", self.cleanup_return_raw)
        self._add_optional_param(post_data, "cleanup.useMetadata", self.cleanup_use_metadata)
        self._add_optional_param(post_data, "download.userAgent", self.download_user_agent)
        self._add_optional_param(post_data, "classifier.maxCategories", self.classifier_max_categories)

        return post_data

    def analyze_url(self, url):
        """Calls the TextRazor API with the provided url.

        TextRazor will first download the contents of this URL, and then process the resulting text.

        TextRazor will only attempt to analyze text documents. Any invalid UTF-8 characters will be replaced with a space character and ignored.
        TextRazor limits the total download size to approximately 1M. Any larger documents will be truncated to that size, and a warning
        will be returned in the response.

        By default, TextRazor will clean all HTML prior to processing. For more control of the cleanup process,
        see the :meth:`set_cleanup_mode' option.

        Returns a :class:`TextRazorResponse` with the parsed data on success.
        Raises a :class:`TextRazorAnalysisException` on failure. """

        post_data = self._build_post_data()
        post_data.append(("url", url.encode("utf-8")))

        return TextRazorResponse(self.do_request("", urlencode(post_data), method="POST"))

    def analyze(self, text):
        """Calls the TextRazor API with the provided unicode text.

        Returns a :class:`TextRazorResponse` with the parsed data on success.
        Raises a :class:`TextRazorAnalysisException` on failure. """

        post_data = self._build_post_data()
        post_data.append(("text", text.encode("utf-8")))

        return TextRazorResponse(self.do_request("", urlencode(post_data), method="POST"))
