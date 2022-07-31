import xml.sax
import xml.sax.handler as sax_handler
from xml.sax.xmlreader import XMLReader


def make_parser() -> XMLReader:
    parser = xml.sax.make_parser()
    parser.setFeature(sax_handler.feature_namespaces, True)
    parser.setFeature(sax_handler.feature_external_ges, False)
    return parser
