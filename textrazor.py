"""
Copyright (c) 2014 TextRazor, http://textrazor.com/

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
    from urllib2 import Request, urlopen, HTTPError, URLError
    from urllib import urlencode
except ImportError:
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
    from urllib.error import HTTPError, URLError

import warnings
import re

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

class TextRazorAnalysisException(BaseException):
    pass

class Topic(object):
    """Represents a single abstract topic extracted from the input text.

    Requires the "topics" extractor to be added to the TextRazor request.
    """

    def __init__(self, topic_json, link_index):
        self._topic_json = topic_json

        for callback, arg in link_index.get(("topic", self.id), []):
            callback(arg, self)

    @property
    def id(self):
        """The unique id of this annotation within its annotation set. """
        return self._topic_json.get("id", None)

    @property
    def label(self):
        """Returns the label for this topic."""
        return self._topic_json.get("label", "")

    @property
    def wikipedia_link(self):
        """Returns a link to Wikipedia for this topic, or None if this topic
        couldn't be linked to a wikipedia page."""
        return self._topic_json.get("wikiLink", None)

    @property
    def score(self):
        """Returns the relevancy score of this topic to the query document."""
        return self._topic_json.get("score", 0)

    def __repr__(self):
        return "TextRazor Topic %s with label %s" % (str(self.id), str(self.label))

    def __str__(self):
        out = ["TextRazor Topic %s and label %s:" % (str(self.id), str(self.label)), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "id":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)

class Entity(object):
    """Represents a single "Named Entity" extracted from the input text.

    Requires the "entities" extractor to be added to the TextRazor request.
    """

    def __init__(self, entity_json, link_index):
        self._response_entity = entity_json
        self._matched_words = []

        for callback, arg in link_index.get(("entity", self.document_id), []):
            callback(arg, self)

        for position in self.matched_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._matched_words.append(word)
        word._add_entity(self)

    @property
    def document_id(self):
        return self._response_entity.get("id", None)

    @property
    def id(self):
        """Returns the disambiguated ID for this entity, or None if this entity
        could not be disambiguated. """
        return self._response_entity.get("entityId", None)

    @property
    def freebase_id(self):
        """Returns the disambiguated Freebase ID for this entity, or None if either
        this entity could not be disambiguated, or a Freebase link doesn't exist."""
        return self._response_entity.get("freebaseId", None)

    @property
    def wikipedia_link(self):
        """Returns a link to Wikipedia for this entity, or None if either this entity
        could not be disambiguated or a Wikipedia link doesn't exist."""
        return self._response_entity.get("wikiLink", None)

    @property
    def matched_text(self):
        """Returns the source text string that matched this entity."""
        return self._response_entity.get("matchedText", None)

    @property
    def starting_position(self):
        return self._response_entity.get("startingPos", None)

    @property
    def ending_position(self):
        return self._response_entity.get("endingPos", None)

    @property
    def matched_positions(self):
        """Returns a list of the token positions in the current sentence that make up this entity."""
        return self._response_entity.get("matchingTokens", [])

    @property
    def matched_words(self):
        """Returns a list of :class:`Word` that make up this entity."""
        return self._matched_words

    @property
    def freebase_types(self):
        """Returns a list of Freebase types for this entity, or an empty list if there are none."""
        return self._response_entity.get("freebaseTypes", [])

    @property
    def relevance_score(self):
        """Returns the relevance this entity has to the source text.  This is a float on a scale of 0 to 1,
        with 1 being the most relevant.  Relevance is determined by the contextual similarity between the entities
        context and facts in the TextRazor knowledgebase."""
        return self._response_entity.get("relevanceScore", None)

    @property
    def confidence_score(self):
        """Returns the confidence that TextRazor is correct that this is a valid entity.  TextRazor uses an ever increasing
        number of signals to help spot valid entities, all of which contribute to this score.  These include the contextual
        agreement between the words in the source text and our knowledgebase, agreement between other entities in the text,
        agreement between the expected entity type and context, prior probabilities of having seen this entity across wikipedia
        and other web datasets.  The score ranges from 0.5 to 10, with 10 representing the highest confidence that this is
        a valid entity."""
        return self._response_entity.get("confidenceScore", None)

    @property
    def dbpedia_types(self):
        """Returns a list of dbpedia types for this entity, or an empty list if there are none."""
        return self._response_entity.get("type", [])

    @property
    def data(self):
        """ Returns a dictionary containing enriched data found for this entity. """
        return self._response_entity.get("data", {})

    def __repr__(self):
        return "TextRazor Entity %s at positions %s" % (self.id.encode("utf-8"), str(self.matched_positions))

    def __str__(self):
        out = ["TextRazor Entity with id:", self.id.encode("utf-8"), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "id":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)


class Entailment(object):
    """Represents a single "entailment" derived from the source text.

    Requires the "entailments" extractor to be added to the TextRazor request.
    """

    def __init__(self, entailment_json, link_index):
        self.entailment_json = entailment_json
        self._matched_words = []

        for callback, arg in link_index.get(("entailment", self.id), []):
            callback(arg, self)

        for position in self.matched_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._matched_words.append(word)
        word._add_entailment(self)

    @property
    def matched_positions(self):
        """Returns the token positions in the current sentence that generated this entailment."""
        return self.entailment_json.get("wordPositions", [])

    @property
    def matched_words(self):
        """Returns links the :class:`Word` in the current sentence that generated this entailment."""
        return self._matched_words

    @property
    def id(self):
        """The unique id of this annotation within its annotation set. """
        return self.entailment_json.get("id", None)

    @property
    def prior_score(self):
        """Returns the score of this entailment independent of the context it is used in this sentence."""
        return self.entailment_json.get("priorScore", None)

    @property
    def context_score(self):
        """Returns the score of agreement between the source word's usage in this sentence and the entailed words
        usage in our knowledgebase."""
        return self.entailment_json.get("contextScore", None)

    @property
    def score(self):
        """Returns the overall confidence that TextRazor is correct that this is a valid entailment, a combination
        of the prior and context score."""
        return self.entailment_json.get("score", None)

    @property
    def entailed_word(self):
        """Returns the word string that is entailed by the source words."""
        entailed_tree = self.entailment_json.get("entailedTree", None)
        if entailed_tree:
            return entailed_tree.get("word", None)

    def __repr__(self):
        return "TextRazor Entailment:\"%s\" at positions %s" % (str(self.entailed_word), str(self.matched_positions))

    def __str__(self):
        out = ["TextRazor Entailment:", str(self.entailed_word), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "id":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)

class RelationParam(object):
    """Represents a Param to a specific :class:`Relation`.

    Requires the "relations" extractor to be added to the TextRazor request."""

    def __init__(self, param_json, relation_parent, link_index):
        self._param_json = param_json
        self._relation_parent = relation_parent
        self._param_words = []

        for position in self.param_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._param_words.append(word)
        word._add_relation_param(self)

    @property
    def relation_parent(self):
        """Returns the :class:`Relation` that owns this param."""
        return self._relation_parent

    @property
    def relation(self):
        """Returns the relation of this param to the predicate:
        Possible values: SUBJECT, OBJECT, OTHER"""
        return self._param_json.get("relation", None)

    @property
    def param_positions(self):
        """Returns a list of the positions of the words in this param within their sentence."""
        return self._param_json.get("wordPositions", [])

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
        return repr(self)

class NounPhrase(object):
    """Represents a multi-word phrase extracted from a sentence.

    Requires the "relations" extractor to be added to the TextRazor request."""

    def __init__(self, noun_phrase_json, link_index):
        self._noun_phrase_json = noun_phrase_json
        self._words = []

        for callback, arg in link_index.get(("nounPhrase", self.id), []):
            callback(arg, self)

        for position in self.word_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, None)]

    def _register_link(self, dummy, word):
        self._words.append(word)
        word._add_noun_phrase(self)

    @property
    def id(self):
        """The unique id of this annotation within its annotation set. """
        return self._noun_phrase_json.get("id", None)

    @property
    def word_positions(self):
        """Returns a list of the positions of the words in this phrase."""
        return self._noun_phrase_json.get("wordPositions", [])

    @property
    def words(self):
        """Returns a list of :class:`Word` that make up this phrase."""
        return self._words

    def __repr__(self):
        return "TextRazor NounPhrase at positions %s" % (str(self.words))

    def __str__(self):
        out = ["TextRazor NounPhrase:", str(self.word_positions), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "word_positions":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)

class Property(object):
    """Represents a property relation extracted from raw text.  A property implies an "is-a" or "has-a" relationship
    between the predicate (or focus) and its property.

    Requires the "relations" extractor to be added to the TextRazor request.
    """

    def __init__(self, property_json, link_index):
        self._property_json = property_json
        self._predicate_words = []
        self._property_words = []

        for callback, arg in link_index.get(("property", self.id), []):
            callback(arg, self)

        for position in self.predicate_positions:
            try:
                link_index[("word", position)].append((self._register_link, True))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, True)]

        for position in self.property_positions:
            try:
                link_index[("word", position)].append((self._register_link, False))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, False)]

    def _register_link(self, is_predicate, word):
        if is_predicate:
            self._predicate_words.append(word)
            word._add_property_predicate(self)
        else:
            self._property_words.append(word)
            word._add_property_properties(self)

    @property
    def id(self):
        """The unique id of this annotation within its annotation set. """
        return self._property_json.get("id", None)

    @property
    def predicate_positions(self):
        """Returns a list of the positions of the words in the predicate (or focus) of this property."""
        return self._property_json.get("wordPositions", [])

    @property
    def predicate_words(self):
        """Returns a list of TextRazor words that make up the predicate (or focus) of this property."""
        return self._predicate_words

    @property
    def property_positions(self):
        """Returns a list of word positions that make up the modifier of the predicate of this property."""
        return self._property_json.get("propertyPositions", [])

    @property
    def property_words(self):
        """Returns a list of :class:`Word` that make up the property that targets the focus words."""
        return self._property_words

    def __repr__(self):
        return "TextRazor Property at positions %s" % (str(self.predicate_positions))

    def __str__(self):
        out = ["TextRazor Property:", str(self.predicate_positions), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "predicate_positions":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)


class Relation(object):
    """Represents a grammatical relation between words.  Typically owns a number of
    :class:`RelationParam`, representing the SUBJECT and OBJECT of the relation.

    Requires the "relations" extractor to be added to the TextRazor request."""

    def __init__(self, relation_json, link_index):
        self._relation_json = relation_json

        self._params = [RelationParam(param, self, link_index) for param in relation_json["params"]]
        self._predicate_words = []

        for callback, arg in link_index.get(("relation", self.id), []):
            callback(arg, self)

        for position in self.predicate_positions:
            try:
                link_index[("word", position)].append((self._register_link, None))
            except KeyError as ex:
                link_index[("word", position)] = [(self._register_link, None)]


    def _register_link(self, dummy, word):
        self._predicate_words.append(word)
        word._add_relation(self)

    @property
    def id(self):
        """The unique id of this annotation within its annotation set. """
        return self._relation_json.get("id", None)

    @property
    def predicate_positions(self):
        """Returns a list of the positions of the predicate words in this relation within their sentence."""
        return self._relation_json.get("wordPositions", [])

    @property
    def predicate_words(self):
        """Returns a list of the TextRazor words in this relation."""
        return self._predicate_words

    @property
    def params(self):
        """Returns a list of the TextRazor params of this relation."""
        return self._params

    def __repr__(self):
        return "TextRazor Relation at positions %s" % (str(self.predicate_words))

    def __str__(self):
        out = ["TextRazor Relation:", str(self.predicate_words), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "predicate_positions":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)

class Word(object):
    """Represents a single Word (token) extracted by TextRazor.

Requires the "words" extractor to be added to the TextRazor request."""

    def __init__(self, response_word, link_index):
        self._response_word = response_word

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

    @property
    def parent_position(self):
        """Returns the position of the grammatical parent of this word, or None if this word is either at the root
        of the sentence or the "dependency-trees" extractor was not requested."""
        return self._response_word.get("parentPosition", None)

    @property
    def parent(self):
        """Returns a link to the TextRazor word that is parent of this word, or None if this word is either at the root
        of the sentence or the "dependency-trees" extractor was not requested."""
        return self._parent

    @property
    def relation_to_parent(self):
        """Returns the Grammatical relation between this word and it's parent, or None if this word is either at the root
        of the sentence or the "dependency-trees" extractor was not requested.

        TextRazor parses into the Stanford uncollapsed dependencies, as detailed at:

        http://nlp.stanford.edu/software/dependencies_manual.pdf
        """
        return self._response_word.get("relationToParent", None)

    @property
    def children(self):
        """Returns a list of TextRazor words that make up the children of this word.  Returns an empty list
        for leaf words, or if the "dependency-trees" extractor was not requested."""
        return self._children

    @property
    def position(self):
        """Returns the position of this word in its sentence."""
        return self._response_word.get("position", None)

    @property
    def stem(self):
        """Returns the stem of this word"""
        return self._response_word.get("stem", None)

    @property
    def lemma(self):
        """Returns the morphological root of this word, see http://en.wikipedia.org/wiki/Lemma_(morphology)
        for details."""
        return self._response_word.get("lemma", None)

    @property
    def token(self):
        """Returns the raw token string that matched this word in the source text."""
        return self._response_word.get("token", None)

    @property
    def part_of_speech(self):
        """Returns the Part of Speech that applies to this word.  We use the Penn treebank tagset,
        as detailed here:

        http://www.comp.leeds.ac.uk/ccalas/tagsets/upenn.html"""
        return self._response_word.get("partOfSpeech", None)

    @property
    def input_start_offset(self):
        """Returns the start offset in the input text for this token.  Note that this offset applies to the
        original Unicode string passed in to the api, TextRazor treats multi byte utf8 charaters as a single position."""
        return self._response_word.get("startingPos", None)

    @property
    def input_end_offset(self):
        """Returns the end offset in the input text for this token.  Note that this offset applies to the
        original Unicode string passed in to the api, TextRazor treats multi byte utf8 charaters as a single position."""
        return self._response_word.get("endingPos", None)

    @property
    def entailments(self):
        """Returns a list of :class:`Entailment` that this word entails."""
        return self._entailments

    @property
    def entities(self):
        """Returns a list of :class:`Entity` that this word is a part of."""
        return self._entities

    @property
    def relations(self):
        """Returns a list of :class:`Relation` that this word is a predicate of."""
        return self._relations

    @property
    def relation_params(self):
        """Returns a list of :class:`RelationParam` that this word is a member of."""
        return self._relation_params

    @property
    def property_properties(self):
        """Returns a list of :class:`Property` that this word is a property member of."""
        return self._property_properties

    @property
    def property_predicates(self):
        """Returns a list of :class:`Property` that this word is a predicate (or focus) member of."""
        return self._property_predicates

    @property
    def noun_phrases(self):
        """Returns a list of :class:`NounPhrase` that this word is a member of."""
        return self._noun_phrases

    @property
    def senses(self):
        """Returns a list of (sense, score) tuples representing scores of each Wordnet sense this this word may be a part of."""
        return self._response_word.get("senses", [])

    def __repr__(self):
        return "TextRazor Word:\"%s\" at position %s" % ((self.token).encode("utf-8"), str(self.position))

    def __str__(self):
        out = ["TextRazor Word:", str(self.token.encode("utf-8")), "\n"]

        for property in dir(self):
            if not property.startswith("_") and not property == "token":
                out.extend([property, ":", repr(getattr(self, property)), "\n"])

        return " ".join(out)

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
            if None != parent_position and parent_position >= 0:
                word._set_parent(word_positions[parent_position])
            else:
                # Punctuation does not get attached to any parent, any non punctuation part of speech
                # must be the root word.
                if word.part_of_speech not in ("$", "``", "''", "(", ")", ",", "--", ".", ":"):
                    self._root_word = word

    @property
    def root_word(self):
        """Returns the root word of this sentence if "dependency-trees" extractor was requested."""
        return self._root_word

    @property
    def words(self):
        """Returns a list of all the :class:`Word` in this sentence."""
        return self._words

class CustomAnnotation(object):

    def __init__(self, annotation_json, link_index):
        self._annotation_json = annotation_json

        for key_value in annotation_json.get("contents", []):
            for link in key_value.get("links", []):
                try:
                    link_index[(link["annotationName"], link["linkedId"])].append((self._register_link, link))
                except Exception as ex:
                    link_index[(link["annotationName"], link["linkedId"])] = [(self._register_link, link)]

    def _register_link(self, link, annotation):
        link["linked"] = annotation

        new_custom_annotation_list = []
        try:
            new_custom_annotation_list = getattr(annotation, self.name());
        except Exception as ex:
            pass
        new_custom_annotation_list.append(self)
        setattr(annotation, self.name(), new_custom_annotation_list)

    def name(self):
        return self._annotation_json["name"]

    def __getattr__(self, attr):
        exists = False
        for key_value in self._annotation_json["contents"]:
            if "key" in key_value and key_value["key"] == attr:
                exists = True
                for link in key_value.get("links", []):
                    try:
                        yield link["linked"]
                    except Exception as ex:
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
        return "TextRazor CustomAnnotation:\"%s\"" % (self._annotation_json["name"])

    def __str__(self):
        out = ["TextRazor CustomAnnotation:", str(self._annotation_json["name"]), "\n"]

        for key_value in self._annotation_json["contents"]:
            try:
                out.append("Param %s:" % key_value["key"])
            except Exception as ex:
                out.append("Param (unlabelled):")
            out.append("\n")
            for link in self.__getattr__(key_value["key"]):
                out.append(repr(link))
                out.append("\n")

        return " ".join(out)

class TextRazorResponse(object):
    """Represents a processed response from TextRazor."""

    def __init__(self, response_json):
        self.response_json = response_json
        self.sentences = []
        self.custom_annotations = []

        link_index = {}

        if "response" in self.response_json:
            # There's a bit of magic here.  Each annotation registers a callback with the ids and types of annotation
            # that it is linked to.  When the linked annotation is later parsed it adds the link via the callback.
            # This means that annotations must be added in order of the dependency between them.

            if "customAnnotations" in self.response_json["response"]:
                self.custom_annotations = [CustomAnnotation(json, link_index) for json in self.response_json["response"]["customAnnotations"]]

            if "topics" in self.response_json["response"]:
                self._topics = [Topic(topic_json, link_index) for topic_json in self.response_json["response"]["topics"]]

            if "coarseTopics" in self.response_json["response"]:
                self._coarse_topics = [Topic(topic_json, link_index) for topic_json in self.response_json["response"]["coarseTopics"]]

            if "entities" in self.response_json["response"]:
                self._entities = [Entity(entity_json, link_index) for entity_json in self.response_json["response"]["entities"]]
            else:
                self._entities = []

            if "entailments" in self.response_json["response"]:
                self._entailments = [Entailment(entailment_json, link_index) for entailment_json in self.response_json["response"]["entailments"]]
            else:
                self._entailments = []

            if "relations" in self.response_json["response"]:
                self._relations = [Relation(relation_json, link_index) for relation_json in self.response_json["response"]["relations"]]
            else:
                self._relations = []

            if "properties" in self.response_json["response"]:
                self._properties = [Property(property_json, link_index) for property_json in self.response_json["response"]["properties"]]
            else:
                self._properties = []

            if "nounPhrases" in self.response_json["response"]:
                self._noun_phrases = [NounPhrase(phrase_json, link_index) for phrase_json in self.response_json["response"]["nounPhrases"]]
            else:
                self._noun_phrases = []

            if "sentences" in self.response_json["response"]:
                self.sentences = [Sentence(sentence_json, link_index) for sentence_json in self.response_json["response"]["sentences"]]

    @property
    def raw_text(self):
        return self.response_json["response"].get("rawText", "")

    @property
    def cleaned_text(self):
        return self.response_json["response"].get("cleanedText", "")

    def summary(self):
        return """Request processed in: %s seconds.  Num Sentences:%s""" % \
                (self.response_json["time"], len(self.response_json["response"]["sentences"]))

    def custom_annotation_output(self):
        """Returns any output generated while running the embedded prolog engine on your rules."""
        return self.response_json["response"].get("customAnnotationOutput", "")

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
        for sentence in self.sentences:
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
        return self.sentences

    def matching_rules(self):
        return [custom_annotation.name() for custom_annotation in self.custom_annotations]

    @property
    def ok(self):
        """Returns True if TextRazor successfully analyzed your document, False if there was some error.
        More detailed information about the error is available in the :meth:`error` property."""
        return self.response_json.get("ok", False)

    @property
    def error(self):
        """Returns a descriptive error message of any problems that may have occurred during analysis,
        or an empty string if there was no error."""
        return self.response_json.get("error", "")

    @property
    def message(self):
        """Returns any warning or informational messages returned from the server."""
        return self.response_json.get("message", "")

    def __getattr__(self, attr):
        exists = False
        for custom_annotation in self.custom_annotations:
            if custom_annotation.name() == attr:
                exists = True
                yield custom_annotation

        if not exists:
            raise AttributeError("TextRazor response has no annotation %r" % attr)

class TextRazor(object):
    """
    The main TextRazor client.  To process your text, create a :class:`TextRazor` instance with your API key
    and set the extractors you need to process the text.  Calls to :meth:`analyze` and :meth:`analyze_url` will then process raw text or URLs
    , returning a :class:`TextRazorResponse` on success.

    This class is threadsafe once initialized with the request options.  You should create a new instance for each request
    if you are likely to be changing the request options in a multithreaded environment.

    Below is an entity extraction example from the tutorial, you can find more examples at http://www.textrazor.com/tutorials.

    >>> client = TextRazor(api_key="DEMO", extractors=["entities"])
    >>> client.set_do_cleanup_HTML(True)
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

    _SECURE_TEXTRAZOR_ENDPOINT = "https://api.textrazor.com/"
    _TEXTRAZOR_ENDPOINT = "http://api.textrazor.com/"

    def __init__(self, api_key, extractors, do_compression=True, do_encryption=False):
        self.api_key = api_key
        self.extractors = extractors
        self.do_compression = do_compression
        self.do_encryption = do_encryption
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

    def set_api_key(self, api_key):
        """Sets the TextRazor API key, required for all requests."""
        self.api_key = api_key

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

    def set_do_compression(self, do_compression):
        """When True, request gzipped responses from TextRazor.  When expecting a large response this can
        significantly reduce bandwidth.  Defaults to True."""
        self.do_compression = do_compression

    def set_do_encryption(self, do_encryption):
        """When True, all communication to TextRazor will be sent over SSL, when handling sensitive
        or private information this should be set to True.  Defaults to False."""
        self.do_encryption = do_encryption

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

    def _add_optional_param(self, post_data, param, value):
        if value != None:
            post_data.append((param, value))

    def _build_post_data(self):
        post_data = [("apiKey", self.api_key),
                     ("rules", self.rules),
                     ("extractors", ",".join(self.extractors)),
                     ("cleanupHTML", self.cleanup_html)]

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

        return post_data

    def _do_request(self, post_data, request_headers):
        encoded_post_data = urlencode(post_data).encode("utf-8")

        if self.do_encryption:
            request = Request(self._SECURE_TEXTRAZOR_ENDPOINT, headers=request_headers, data=encoded_post_data)
        else:
            request = Request(self._TEXTRAZOR_ENDPOINT, headers=request_headers, data=encoded_post_data)

        try:
            response = urlopen(request)
        except HTTPError as e:
            raise TextRazorAnalysisException("TextRazor returned HTTP Code %d: %s" % (e.code, e.read()))
        except URLError as e:
            raise TextRazorAnalysisException("Could not connect to TextRazor")

        if response.info().get('Content-Encoding') == 'gzip':
            buf = IOStream( response.read())
            response = gzip.GzipFile(fileobj=buf)

        response_json = json.loads(response.read().decode("utf-8"))

        return TextRazorResponse(response_json)

    def _build_request_headers(self):
        request_headers = {}

        if self.do_compression:
            request_headers['Accept-encoding'] = 'gzip'

        return request_headers

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

        return self._do_request(post_data, self._build_request_headers())


    def analyze(self, text):
        """Calls the TextRazor API with the provided unicode text.

        Returns a :class:`TextRazorResponse` with the parsed data on success.
        Raises a :class:`TextRazorAnalysisException` on failure. """

        post_data = self._build_post_data()
        post_data.append(("text", text.encode("utf-8")))

        return self._do_request(post_data, self._build_request_headers())
