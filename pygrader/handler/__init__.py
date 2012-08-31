# Copyright

"Define assorted handlers for use in :py:mod:`~pygrader.mailpipe`."

from ..email import construct_response as _construct_response


def respond(course, person, original, subject, text, respond):
    "Helper for composing consistent response messages."
    response_text = (
        '{},\n\n'
        '{}\n\n'
        'Yours,\n{}').format(
        person.alias(), text, course.robot.alias())
    response = _construct_response(
        author=course.robot, targets=[person],
        subject=subject, text=response_text,
        original=original)
    respond(response)
