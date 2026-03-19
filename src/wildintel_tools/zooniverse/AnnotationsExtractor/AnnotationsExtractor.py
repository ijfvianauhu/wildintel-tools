from typing import List, Any

from wildintel_tools.zooniverse.Schemas import ClassificationInfo

class AnnotationsExtractor:
    """
    This class extracts annotations from Zooniverse classifications. It
    receives a list of ClassificationInfo objects for a specific subject
    and processes them to extract information that will be analysed by
    the AnnotationsVoter.

    Also, this class should convert the species names from Zooniverse to Trapper. Each choice should be assigned its
    scientific name when applicable—whether it refers to an animal or a human. In other cases, we should use
    ‘vehicle’, ‘blank’, ‘unclassified’, or ‘unknown’.

    It is important to note that this class does not perform any voting or
    aggregation of annotations; its sole purpose is to extract and format
    the raw annotation data from the classifications.


    For example, given the following classifications for the subject 'oth sp_4.jpeg':

    [
  ClassificationInfo(
    classification_id='664345585',
    user_name='zenscientist',
    user_id='2710015',
    annotations=[
      {
        'task': 'T0',
        'value': [
          {
            'choice': 'OTHERSPECIES',
            'answers': {},
            'filters': {}
          }
        ]
      }
    ],
    subject_name='oth sp_4.jpeg',
    retired=True,
    retirement_reason='classification_count',
    sid = 12345
  ),

  ClassificationInfo(
    classification_id='673798541',
    user_name='not-logged-in-ecb4b0fc5337a0d6f1b3',
    user_id='',
    annotations=[
      {
        'task': 'T0',
        'value': [
          {
            'choice': 'COMMONGENET',
            'answers': {'HOWMANY': '1'},
            'filters': {}
          }
        ]
      }
    ],
    subject_name='oth sp_4.jpeg',
    retired=True,
    retirement_reason='classification_count',
    sid = 12345
  ),

  ClassificationInfo(
    classification_id='674120196',
    user_name='not-logged-in-1f4e165e287ada726e08',
    user_id='',
    annotations=[
      {
        'task': 'T0',
        'value': []
      }
    ],
    subject_name='oth sp_4.jpeg',
    retired=True,
    retirement_reason='classification_count'
    sid = 12345
  )
]
    It could extract the following list of choices and answers:

    [('OTHERSPECIES', {}), ('OTHERSPECIES', {}),('Genetta genetta', {'HOWMANY': '1'})]

    As shown in the example above, the class processes each classification,
    extracts the choices made by users along with any associated answers,
    and compiles them into a list of tuples for further analysis. Note that choice COMMONGENET has been converted to its
     scientific name "Genetta genetta" and  OTHERSPECIES to "unknown" as per the mapping rules.

    """

    @staticmethod
    def run(classifications:List[ClassificationInfo]) -> List[Any]:
        pass
