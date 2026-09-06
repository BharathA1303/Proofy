"""
backend/app/services/face/__init__.py

Module 4: Biometric Verification & Presentation Attack Detection.
"""
from app.services.face.arcface_embedding import ArcFaceEmbeddingModel
from app.services.face.face_aligner import FaceAligner
from app.services.face.face_detector import FaceDetector, face_detector
from app.services.face.face_matcher import compare_face_embeddings
from app.services.face.face_quality import evaluate_face_quality
from app.services.face.face_verification_service import (
    FaceVerificationService,
    face_verification_service,
    verify_passport_biometrics,
)
from app.services.face.minifasnet_pad import MiniFASNetPAD
from app.services.face.secondary_pad import SecondaryOpticalPAD
from app.services.face.session_store import session_document_store

__all__ = [
    "FaceDetector",
    "face_detector",
    "FaceAligner",
    "evaluate_face_quality",
    "ArcFaceEmbeddingModel",
    "MiniFASNetPAD",
    "SecondaryOpticalPAD",
    "compare_face_embeddings",
    "session_document_store",
    "FaceVerificationService",
    "face_verification_service",
    "verify_passport_biometrics",
]
