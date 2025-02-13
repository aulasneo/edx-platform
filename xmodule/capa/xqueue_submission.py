"""
This module provides an interface for submitting student responses
to an external grading system through XQueue.
"""

import json
import logging
import re
from opaque_keys.edx.keys import CourseKey

log = logging.getLogger(__name__)

class XQueueInterfaceSubmission:
    """Interface to the external grading system."""

    def _parse_json(self, data, name):
        """Helper function to parse JSON safely."""
        try:
            return json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing {name}: {e}") from e

    def _extract_identifiers(self, callback_url):
        """Extracts identifiers from the callback URL."""
        item_id_match = re.search(r'block@([^\/]+)', callback_url)
        item_type_match = re.search(r'type@([^+]+)', callback_url)
        course_id_match = re.search(r'(course-v1:[^\/]+)', callback_url)
        max_score_match = re.search(r'(\d+(\.\d+)?)$', callback_url)

        if not all([item_id_match, item_type_match, course_id_match, max_score_match]):
            raise ValueError("The callback_url does not contain the required information.")

        return (
            item_id_match.group(1),
            item_type_match.group(1),
            course_id_match.group(1),
            float(max_score_match.group(1))
        )

    def extract_item_data(self, header, payload):
        """
        Extracts student submission data from the given header and payload.
        """

        header = self._parse_json(header, "header")
        payload = self._parse_json(payload, "payload")

        callback_url = header.get('lms_callback_url')
        queue_name = header.get('queue_name', 'default')

        if not callback_url:
            raise ValueError("The header does not contain 'lms_callback_url'.")

        item_id, item_type, course_id, max_score = self._extract_identifiers(callback_url)

        student_info = self._parse_json(payload["student_info"], "student_info")

        full_block_id = None

        try:
            full_block_id = (
                f"block-v1:{course_id.replace('course-v1:', '')}+type@{item_type}+block@{item_id}"
            )
        except Exception as e:
            raise ValueError(
                f"Error creating BlockUsageLocator. Invalid ID: {full_block_id}, Error: {e}"
            ) from e

        try:
            course_key = CourseKey.from_string(course_id)
        except Exception as e:
            raise ValueError(f"Error creating CourseKey: {e}") from e

        try:
            grader_payload = self._parse_json(payload["grader_payload"], "grader_payload")
            grader = grader_payload.get("grader", '')
        except KeyError as e:
            raise ValueError(f"Error in payload: {e}") from e

        student_id = student_info.get("anonymous_student_id")
        if not student_id:
            raise ValueError("The field 'anonymous_student_id' is missing from student_info.")

        student_dict = {
            'item_id': full_block_id,
            'item_type': item_type,
            'course_id': course_id,
            'student_id': student_id
        }

        student_answer = payload.get("student_response")
        if student_answer is None:
            raise ValueError("The field 'student_response' does not exist.")

        score = max_score

        return student_dict, student_answer, queue_name, grader, score

    def send_to_submission(self, header, body, files_to_upload=None):
        """
        Submits the extracted student data to the edx-submissions system.
        """
        from submissions.api import create_submission

        try:
            student_item, answer, queue_name, grader, score = self.extract_item_data(header, body)
            return create_submission(student_item, answer, queue_name=queue_name, grader=grader, score=score)

        except json.JSONDecodeError as e:
            log.error("JSON decoding error: %s", e)
            return {"error": "Invalid JSON format"}

        except KeyError as e:
            log.error("Missing key: %s", e)
            return {"error": f"Missing key: {e}"}

        except ValueError as e:
            log.error("Validation error: %s", e)
            return {"error": f"Validation error: {e}"}

        except TypeError as e:
            log.error("Type error: %s", e)
            return {"error": f"Type error: {e}"}

        except RuntimeError as e:
            log.error("Runtime error: %s", e)
            return {"error": f"Runtime error: {e}"}
