"""Small, authored teaching fixtures. No network research or model inference occurs here."""
from .contracts import Curriculum, LessonContent, Grade, Audit
from .providers import ProviderError


CORPUS = {
    'vectors': {
        'title': 'Vectors and weighted sums', 'suite': 'neural', 'minutes': 15,
        'keywords': ['vector', 'weighted sum', 'input'],
        'text': 'A vector is an ordered list of numbers. A neural network represents input features as numbers in a vector. A weighted sum multiplies corresponding inputs and weights and adds a bias. For x=[2,3], w=[0.5,-1], b=1, the result is 2*0.5+3*(-1)+1=-1. In Python, sum(xi*wi for xi,wi in zip(x,w))+b computes this when the lists have equal lengths. Feature order must match weight order. Check list lengths and compare a small hand calculation with the code.',
        'example': 'Let x=[2,3], w=[0.5,-1] and b=1. First multiply: 2×0.5=1 and 3×(-1)=-3. Add the bias: 1-3+1=-1. Python: sum(xi*wi for xi,wi in zip(x,w))+b. Verify the result is -1 and that the input and weight lists have equal length.',
        'prompt': 'What is the weighted sum for x=[2,3], w=[0.5,-1], b=1?',
        'options': ['-1', '0', '3'], 'answer': '-1',
        'transfer': 'You swap the order of two input features but keep the weights in their original order. Why can the prediction change?',
        'rubric': ['Features must match the corresponding weights', 'Changing the pairing can change the weighted sum'],
        'terms': ['weight', 'sum'],
    },
    'forward-pass': {
        'title': 'A neuron and the forward pass', 'suite': 'neural', 'minutes': 20,
        'keywords': ['activation', 'neuron', 'forward'],
        'text': 'A neuron computes a weighted sum and then an activation function. ReLU(z)=max(0,z). With weighted sum -1, ReLU produces 0; with 4 it produces 4. A forward pass applies these operations layer by layer to make a prediction. Nonlinear activation lets multiple layers model nonlinear relationships; composing only linear transformations is still linear (or affine when biases are present). Check a neuron by calculating its weighted sum and activation separately.',
        'example': 'For a neuron with pre-activation z=-1, ReLU returns max(0,-1)=0. If z=4 it returns 4. Check each stage separately: first the weighted sum, then the activation. Python: max(0, z).',
        'prompt': 'What does ReLU return for z=-1?', 'options': ['0', '-1', '1'], 'answer': '0',
        'transfer': 'Why do several layers with only linear transformations fail to model a nonlinear relationship?',
        'rubric': ['Composition of linear transformations remains linear', 'A nonlinear activation is needed to model nonlinear relationships'],
        'terms': ['linear', 'activation'],
    },
    'training': {
        'title': 'Loss, training and validation', 'suite': 'neural', 'minutes': 25,
        'keywords': ['loss', 'gradient', 'validation'],
        'text': 'Loss measures prediction error. For one squared-error example, prediction 3 and target 1 give loss (3-1)^2=4. Gradient descent adjusts weights opposite the loss gradient: w_new=w-learning_rate*gradient. If w=0.5, learning_rate=0.1 and gradient=2, the new weight is 0.3. Backpropagation computes gradients through the network. Held-out validation data estimates performance on unseen examples; training loss alone cannot establish generalization. Training and validation performance can differ due to overfitting.',
        'example': 'A prediction of 3 with target 1 gives squared error 4. With w=0.5, learning rate 0.1 and gradient 2, update w to 0.5-0.1×2=0.3. Check performance on separate validation examples as well as the training set.',
        'prompt': 'Using w=0.5, learning rate 0.1, gradient 2, what is the new weight?', 'options': ['0.3', '0.7', '2'], 'answer': '0.3',
        'transfer': 'Training loss falls, but validation error rises. What could explain this, and why keep validation data separate?',
        'rubric': ['Overfitting can reduce training error while hurting unseen performance', 'Validation estimates performance on unseen data'],
        'terms': ['overfit', 'unseen'],
    },
    'relations': {
        'title': 'Relations and keys', 'suite': 'database', 'minutes': 15,
        'keywords': ['relation', 'primary key', 'foreign key'],
        'text': 'A relational table stores rows with named attributes. A primary key uniquely identifies each row and does not allow null values. A foreign key constrains values to reference a key in another or the same table. In Student(id,name) and Enrollment(student_id,course_id), Student.id may be the primary key and Enrollment.student_id a foreign key. A student can have several enrollment rows, so student_id alone need not uniquely identify Enrollment. A composite key such as (student_id,course_id) can identify an enrollment if each student enrolls in each course at most once.',
        'example': 'Student has rows (1,Ada) and (2,Lin). Enrollment has (1,DB) and (1,AI). Student.id is unique, while Enrollment.student_id repeats. Under the one-enrollment-per-course rule, (student_id,course_id) identifies an enrollment.',
        'prompt': 'Which property is required of a primary key?', 'options': ['Unique and non-null', 'Always text', 'Always a single column'], 'answer': 'Unique and non-null',
        'transfer': 'Why can student_id be a foreign key without being the primary key of Enrollment?',
        'rubric': ['A foreign key references a key in the related table', 'A student may have multiple enrollment rows so student_id is not unique there'],
        'terms': ['refer', 'multiple'],
    },
    'joins': {
        'title': 'Joins and query reasoning', 'suite': 'database', 'minutes': 20,
        'keywords': ['join', 'sql', 'matching'],
        'text': 'An INNER JOIN returns matching row combinations under its join condition. A LEFT JOIN also preserves left rows with no match, placing nulls in right-side columns. If Student has Ada and Lin, and only Ada has an Enrollment, an inner join on Student.id=Enrollment.student_id omits Lin; a left join includes Lin with null enrollment columns. One left row with two right matches yields two joined rows. A WHERE filter requiring a right-side value after a left join can remove null-extended rows.',
        'example': 'SELECT s.name, e.course_id FROM Student s LEFT JOIN Enrollment e ON s.id=e.student_id; If Ada has DB and AI enrollments and Lin has none, the result has (Ada,DB), (Ada,AI), (Lin,NULL). Predict the three rows before running the query.',
        'prompt': 'Which join preserves students with no matching enrollment?', 'options': ['LEFT JOIN from Student', 'INNER JOIN', 'No join does'], 'answer': 'LEFT JOIN from Student',
        'transfer': 'A left join is followed by WHERE e.course_id = \'DB\'. Why might a student with no enrollment disappear?',
        'rubric': ['An unmatched right-side course_id is NULL', 'The WHERE equality filter does not retain this null-extended row'],
        'terms': ['null', 'where'],
    },
    'normalization': {
        'title': 'Dependencies and normalization', 'suite': 'database', 'minutes': 25,
        'keywords': ['dependency', 'normalization', 'anomaly'],
        'text': 'A functional dependency X -> Y means rows agreeing on X must agree on Y. Repeating department names for each student can cause update anomalies when the same department name must be changed in many rows. If student_id -> department_id and department_id -> department_name, store departments separately and reference them from students to remove that repeated department fact. Decomposition must preserve the intended information through a lossless join. Normalization decisions depend on actual dependencies, not column names alone.',
        'example': 'Student(1,D1,Computing) and Student(2,D1,Computing) repeat the name for D1. Split into Student(student_id,department_id) and Department(department_id,department_name). Changing D1’s name now changes one Department row. Check that a join recovers the original student-department facts.',
        'prompt': 'What does a functional dependency X -> Y mean?', 'options': ['Equal X implies equal Y', 'X and Y are identical', 'Y is always numeric'], 'answer': 'Equal X implies equal Y',
        'transfer': 'Why split a repeated department name into a Department table, and what must you check after decomposition?',
        'rubric': ['Separate the repeated fact to avoid update anomalies', 'Check that the decomposition supports a lossless join'],
        'terms': ['anomal', 'lossless'],
    },
}


def suite(text):
    if any(word in text.lower() for word in ('database', 'sql', 'relation', 'join', 'normalization', 'department', 'primary key')):
        return 'database'
    if any(word in text.lower() for word in ('neural', 'vector', 'activation', 'gradient', 'training', 'weighted', 'loss')):
        return 'neural'
    raise ProviderError('Fixture mode supports neural networks and databases only. Use one of the demo examples or configure live providers.')


class FixtureSearch:
    def search(self, query):
        group = suite(query)
        return [{'url': f'fixture://{key}', 'title': f'FIXTURE — {v["title"]}', 'snippet': v['text'][:120]} for key, v in CORPUS.items() if v['suite'] == group]


class FixtureGenerator:
    def generate(self, schema, instruction, data):
        if schema is Curriculum:
            group = suite(data['task']['objective'])
            topics, previous = [], []
            for key, item in CORPUS.items():
                if item['suite'] == group:
                    topics.append({'id': key, 'title': item['title'], 'objective': f'Explain and apply {item["title"].lower()}.', 'prerequisites': previous[-1:], 'keywords': item['keywords'], 'estimated_minutes': item['minutes'], 'practice': 'Solve a worked calculation, then explain a changed scenario.'})
                    previous.append(key)
            return Curriculum(topics=topics, assumptions=['Fixture curriculum is authored in English for the selected demonstration domain.', 'Unassessed topics are provisionally unknown; the first check acts as a short diagnostic.'], scope_status='supplied' if data['has_scope'] else ('provisional' if data['task']['purpose'] == 'exam' else 'not_applicable'))
        if schema is LessonContent:
            topic = data['topic']
            item = CORPUS[topic['id']]
            evidence = next((p for p in data['passages'] if p['reference'] == 'fixture://' + topic['id']), None)
            if evidence is None:
                raise ProviderError('Fixture lesson requires its authored fixture passage; it cannot fabricate support from a supplied document.')
            cite = [{'source_id': evidence['source_id'], 'passage_id': evidence['passage_id']}]
            mode = data['task']['purpose']
            support = data.get('variant') == 'support'
            explanation = '. '.join(item['text'].split('. ')[:2]) + '.' if support else item['text']
            sections = [{'heading': 'Focused support: start here' if support else 'Core explanation', 'text': explanation, 'citations': cite}, {'heading': 'Worked example — check each step', 'text': item['example'], 'citations': cite}]
            if mode == 'practical':
                sections.append({'heading': 'Do it and verify', 'text': 'Follow the worked example one step at a time. Write the intermediate values or rows before checking the stated result. If the result differs, check the first differing step against the source passage.', 'citations': cite})
            elif mode == 'long_term':
                sections.append({'heading': 'Apply it to a new situation', 'text': item['transfer'] + ' Explain the mechanism, rather than only repeating a definition.', 'citations': cite})
            else:
                sections.append({'heading': 'Generated exam-style practice', 'text': item['transfer'] + ' State your reasoning explicitly. This authored practice is not a prediction of exam questions or topic weights.', 'citations': cite})
            return LessonContent(title=('Focused support: ' if support else '') + item['title'], objectives=[topic['objective']], prerequisites=topic['prerequisites'], sections=sections, questions=[
                {'id': 'check', 'topic_id': topic['id'], 'kind': 'choice', 'prompt': item['prompt'], 'options': item['options'], 'answer': item['answer'], 'rubric': ['Choose the supported answer'], 'difficulty': 'application', 'citations': cite},
                {'id': 'transfer', 'topic_id': topic['id'], 'kind': 'short_text', 'prompt': item['transfer'], 'answer': '; '.join(item['rubric']), 'rubric': item['rubric'], 'difficulty': 'transfer', 'citations': cite},
            ], limitations=['FIXTURE lesson: authored demonstration, not live web research or AI generation.'])
        if schema is Grade:
            item = CORPUS[data['question']['topic_id']]
            terms = item['terms']
            hits = sum(term in data['answer'].lower() for term in terms)
            return Grade(score=hits / len(terms), confidence=0.45, feedback='Fixture keyword check only; this cannot establish understanding. Compare your reasoning to: ' + '; '.join(item['rubric']), criteria_met=[term for term in terms if term in data['answer'].lower()])
        if schema is Audit:
            return Audit(support='uncertain', explanation='Fixture mode does not perform semantic support or contradiction checking. Citation IDs are validated separately.', disagreements=[])
        raise ProviderError('Unsupported fixture operation.')
