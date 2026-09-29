"""Generate two tiny text PDF fixtures with no third-party dependency.

These are authored demonstration lectures, not documents from a real course.
Run: python examples/make_pdfs.py
"""
from pathlib import Path


def pdf_bytes(lines):
    content = 'BT /F1 11 Tf 50 780 Td 16 TL\n'
    for index, line in enumerate(lines):
        escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        content += ('T* ' if index else '') + f'({escaped}) Tj\n'
    content += 'ET\n'
    stream = content.encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'endstream']
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


if __name__ == '__main__':
    root = Path(__file__).parent
    (root / 'lecture-1-keys.pdf').write_bytes(pdf_bytes([
        'AUTHORED FIXTURE LECTURE 1: RELATIONS AND KEYS',
        'A relational table has rows with named attributes.',
        'A primary key uniquely identifies a row and cannot be null.',
        'A foreign key references a key in another or the same table.',
        'Student(id, name) can use id as its primary key.',
        'Enrollment(student_id, course_id) references Student.id.',
        'A student may enroll in several courses, so student_id can repeat.',
        'A composite key (student_id, course_id) can identify an enrollment',
        'when each student enrolls in a given course at most once.',
    ]))
    (root / 'lecture-2-joins.pdf').write_bytes(pdf_bytes([
        'AUTHORED FIXTURE LECTURE 2: SQL JOINS',
        'An INNER JOIN returns matching row combinations.',
        'A LEFT JOIN also preserves unmatched rows from its left table.',
        'Unmatched right-side columns contain NULL in those rows.',
        'Ada has enrollments DB and AI; Lin has no enrollment.',
        'A left join from Student to Enrollment returns three rows:',
        '(Ada, DB), (Ada, AI), and (Lin, NULL).',
        'A WHERE filter requiring e.course_id = DB can remove Lin.',
        'Normalization is outside this lecture and requires another source.',
    ]))
    print('Created two authored text PDF fixtures in examples/.')
