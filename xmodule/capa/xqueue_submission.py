"""
LMS Interface to external queueing system (xqueue)
"""
from typing import Dict, Optional, TYPE_CHECKING

import hashlib
import json
import logging

import requests
from django.conf import settings
from django.urls import reverse
from requests.auth import HTTPBasicAuth
import re
from xmodule.capa.util import construct_callback
from opaque_keys.edx.keys import CourseKey, UsageKey
from django.core.exceptions import ObjectDoesNotExist
#rom lms.djangoapps.lti_provider.outcomes import send_score_update
log = logging.getLogger(__name__)
dateformat = '%Y-%m-%dT%H:%M:%S'


XQUEUE_METRIC_NAME = 'edxapp.xqueue'

# Wait time for response from Xqueue.
XQUEUE_TIMEOUT = 35  # seconds
CONNECT_TIMEOUT = 3.05  # seconds
READ_TIMEOUT = 10  # seconds



def extract_item_data(header, payload):
    from lms.djangoapps.courseware.models import StudentModule
    from opaque_keys.edx.locator import BlockUsageLocator
    """
    Extrae la información del estudiante, módulo y curso desde el header y payload.
    Además, obtiene la calificación (score) desde la base de datos.
    """
    if isinstance(header, str):
        try:
            header = json.loads(header)
        except json.JSONDecodeError as e:
            raise ValueError(f"Error to header: {e}")

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"Error to payload: {e}")

    callback_url = header.get('lms_callback_url')
    queue_name = header.get('queue_name', '')

    if not callback_url:
        raise ValueError("El header is not content 'lms_callback_url'.")

    match_item_id = re.search(r'(block-v1:[^/]+)', callback_url)
    match_course_id = re.search(r'(course-v1:[^\/]+)', callback_url)
    match_item_type = re.search(r'type@([^+]+)', callback_url)

    if not (match_item_id and match_item_type and match_course_id):
        raise ValueError(f"The callback_url is not valid: {callback_url}")

    item_id = match_item_id.group(1)
    item_type = match_item_type.group(1)
    course_id = match_course_id.group(1)

    # Convertir item_id y course_id a UsageKey y CourseKey
    #try:
    usage_key = BlockUsageLocator.from_string(item_id)
    course_key = CourseKey.from_string(course_id)
    #except Exception as e:
    #    raise ValueError(f"Error converting item_id or course_id to keys: {e}")

    try:
        student_info = json.loads(payload["student_info"])
    except json.JSONDecodeError as e:
        raise ValueError(f"Error to student_info: {e}")

    student_id = student_info.get("anonymous_student_id")
    if not student_id:
        raise ValueError("The field 'anonymous_student_id' is not student_info.")

    student_dict = {
        'item_id': item_id,
        'item_type': item_type,
        'course_id': course_id,
        'student_id': student_id
    }

    # Obtener la respuesta del estudiante
    student_answer = payload.get("student_response")
    if student_answer is None:
        raise ValueError("El campo 'student_response' no está presente en payload.")

    # Obtener el módulo del estudiante y su calificación
    student_module = StudentModule.objects.filter(
        module_state_key=usage_key,
        course_id=course_key
    ).first()

    log.error(f"student_module: {student_module}")
    
    if student_module and student_module.grade is not None:
        score = student_module.grade
    else:
        score = None  # Si no hay calificación aún

    log.error(f"Score obtain {student_id}: {score}")

    
    return student_dict, student_answer, queue_name, score

class XQueueInterfaceSubmission:
    """
    Interface to the external grading system
    """    

    def get_score(self,score):
        
        return score
    
    def send_to_submission(self, header, body, files_to_upload=None):
        #try:
            from submissions.api import create_submission
            student_item, answer, queue_name, score = extract_item_data(header, body)

            log.error(f"student_item: {student_item}")
            log.error(f"header: {header}")
            log.error(f"body: {body}")
            log.error(f"score: {score}")

            # Pasar el score a create_submission
            submission = create_submission(student_item, answer, queue_name=queue_name, score=score)

            return submission
        #except Exception as e:
            #return {"error": str(e)}