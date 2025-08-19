import os
import re
from datetime import datetime, timedelta
from scaleway import Client
from scaleway.registry.v1 import RegistryV1API

def is_tag_old(tag):
    """Vérifie si un tag a été créé ou mis à jour il y a plus de 3 mois"""
    try:
        # Récupérer les dates created_at et updated_at
        created_at = tag.created_at
        updated_at = tag.updated_at
        
        # Prendre la date la plus récente entre created_at et updated_at
        most_recent_date = max(created_at, updated_at)
        
        # Calculer la date limite (3 mois = 90 jours)
        cutoff_date = datetime.now(tz=most_recent_date.tzinfo) - timedelta(days=90)
        
        return most_recent_date < cutoff_date
        
    except Exception as e:
        print(f"Erreur lors de la vérification de l'âge du tag {tag.id}: {e}")
        return False

def should_delete_tag_by_name(tag, name_pattern):
    """Vérifie si un tag doit être supprimé en fonction de son nom (regex)"""
    if not name_pattern:
        return False
    
    try:
        # Compiler la regex et vérifier si le nom du tag correspond
        pattern = re.compile(name_pattern)
        return bool(pattern.search(tag.name))
    except re.error as e:
        print(f"Erreur dans la regex '{name_pattern}': {e}")
        return False
    except Exception as e:
        print(f"Erreur lors de la vérification du nom du tag {tag.id}: {e}")
        return False

def handle(event, context):
    # Configuration
    region = os.environ['REGION']
    
    # Variables optionnelles pour les différents modes de suppression
    delete_old_tags = os.environ.get('DELETE_OLD_TAGS', 'true').lower() == 'true'
    tag_name_pattern = os.environ.get('TAG_NAME_PATTERN', None)  # Regex pour matcher les noms de tags
    delete_unused_namespaces = os.environ.get('DELETE_UNUSED_NAMESPACE', 'false').lower() == 'true'
    target_namespace_id = os.environ.get('NAMESPACE_ID', None)  # ID du namespace spécifique à cibler
    
    # Initialiser le client Scaleway
    client = Client.from_config_file_and_env()
    registry_api = RegistryV1API(client)
    
    tags_to_delete = []
    namespaces_to_delete = []
    
    try:
        # Récupérer toutes les images (pagination automatique avec le SDK)
        # Si un namespace spécifique est ciblé, filtrer les images par namespace
        if target_namespace_id:
            images_response = registry_api.list_images_all(
                region=region,
                namespace_id=target_namespace_id,
                order_by="created_at_asc"
            )
            print(f"Trouvé {len(images_response)} images à analyser dans le namespace {target_namespace_id}")
        else:
            images_response = registry_api.list_images_all(
                region=region,
                order_by="created_at_asc"
            )
            print(f"Trouvé {len(images_response)} images à analyser dans tous les namespaces")
        
        # Parcourir chaque image pour récupérer ses tags
        for image in images_response:
            try:
                # Récupérer tous les tags de l'image
                tags_response = registry_api.list_tags_all(
                    region=region,
                    image_id=image.id,
                    order_by="created_at_desc"
                )
                
                # Filtrer les tags selon les critères configurés
                for tag in tags_response:
                    should_delete = False
                    deletion_reason = []
                    
                    # Vérifier si le tag est ancien (si activé)
                    if delete_old_tags and is_tag_old(tag):
                        should_delete = True
                        deletion_reason.append("old")
                    
                    # Vérifier si le nom du tag correspond au pattern (si défini)
                    if tag_name_pattern and should_delete_tag_by_name(tag, tag_name_pattern):
                        should_delete = True
                        deletion_reason.append("name_match")
                    
                    if should_delete:
                        tags_to_delete.append({
                            'tag': tag,
                            'reason': deletion_reason
                        })
                        
            except Exception as e:
                print(f"Erreur lors de la récupération des tags pour l'image {image.id}: {e}")
                continue
        
        print(f"Trouvé {len(tags_to_delete)} tags à supprimer")
        
        # Afficher un résumé des critères utilisés
        criteria_summary = []
        if delete_old_tags:
            criteria_summary.append("tags anciens (>3 mois)")
        if tag_name_pattern:
            criteria_summary.append(f"tags matchant le pattern: '{tag_name_pattern}'")
        if delete_unused_namespaces:
            criteria_summary.append("namespaces vides")
        if target_namespace_id:
            criteria_summary.append(f"namespace ciblé: {target_namespace_id}")
        
        if criteria_summary:
            print(f"Critères de suppression actifs: {', '.join(criteria_summary)}")
        else:
            print("Aucun critère de suppression actif")
        
        # Supprimer les tags correspondants
        msg = []
        deleted_count = 0
        
        for tag_info in tags_to_delete:
            tag = tag_info['tag']
            reasons = tag_info['reason']
            
            try:
                # Supprimer le tag
                registry_api.delete_tag(
                    region=region,
                    tag_id=tag.id
                )
                
                msg.append({
                    "tag_id": tag.id,
                    "tag_name": tag.name,
                    "image_name": getattr(tag, 'image_name', 'unknown'),
                    "status": "deleted",
                    "deletion_reasons": reasons,
                    "created_at": tag.created_at.isoformat(),
                    "updated_at": tag.updated_at.isoformat()
                })
                deleted_count += 1
                print(f"Tag supprimé: {tag.name} (ID: {tag.id}) - Raisons: {', '.join(reasons)}")
                
            except Exception as e:
                msg.append({
                    "tag_id": tag.id,
                    "tag_name": tag.name,
                    "status": "error",
                    "deletion_reasons": reasons,
                    "error": str(e)
                })
                print(f"Erreur lors de la suppression du tag {tag.id}: {e}")
        
        # Gestion des namespaces vides (si activée)
        deleted_namespaces_count = 0
        namespace_errors = 0
        
        if delete_unused_namespaces:
            try:
                # Si un namespace spécifique est ciblé, ne vérifier que celui-ci
                if target_namespace_id:
                    # Récupérer le namespace spécifique
                    try:
                        namespace = registry_api.get_namespace(
                            region=region,
                            namespace_id=target_namespace_id
                        )
                        namespaces_to_check = [namespace]
                        print(f"Vérification du namespace ciblé {target_namespace_id} pour suppression s'il est vide")
                    except Exception as e:
                        print(f"Erreur lors de la récupération du namespace {target_namespace_id}: {e}")
                        namespaces_to_check = []
                else:
                    # Récupérer tous les namespaces
                    namespaces_to_check = registry_api.list_namespaces_all(region=region)
                    print(f"Vérification de {len(namespaces_to_check)} namespaces pour suppression des namespaces vides")
                
                for namespace in namespaces_to_check:
                    try:
                        # Vérifier si le namespace contient des images
                        images_in_namespace = registry_api.list_images_all(
                            region=region,
                            namespace_id=namespace.id
                        )
                        
                        # Si le namespace est vide, le marquer pour suppression
                        if len(images_in_namespace) == 0:
                            try:
                                registry_api.delete_namespace(
                                    region=region,
                                    namespace_id=namespace.id
                                )
                                
                                msg.append({
                                    "namespace_id": namespace.id,
                                    "namespace_name": namespace.name,
                                    "status": "deleted",
                                    "type": "namespace",
                                    "reason": "empty_namespace"
                                })
                                deleted_namespaces_count += 1
                                print(f"Namespace vide supprimé: {namespace.name} (ID: {namespace.id})")
                                
                            except Exception as e:
                                msg.append({
                                    "namespace_id": namespace.id,
                                    "namespace_name": namespace.name,
                                    "status": "error",
                                    "type": "namespace",
                                    "reason": "empty_namespace",
                                    "error": str(e)
                                })
                                namespace_errors += 1
                                print(f"Erreur lors de la suppression du namespace {namespace.id}: {e}")
                        
                    except Exception as e:
                        print(f"Erreur lors de la vérification du namespace {namespace.id}: {e}")
                        namespace_errors += 1
                        continue
                        
            except Exception as e:
                print(f"Erreur lors de la récupération des namespaces: {e}")
                namespace_errors += 1
        
        return {
            "body": {
                "message": msg,
                "summary": {
                    "total_images_analyzed": len(images_response),
                    "total_tags_found": len(tags_to_delete),
                    "successfully_deleted": deleted_count,
                    "errors": len(tags_to_delete) - deleted_count,
                    "namespaces_deleted": deleted_namespaces_count if delete_unused_namespaces else 0,
                    "namespace_errors": namespace_errors if delete_unused_namespaces else 0,
                    "criteria_used": {
                        "delete_old_tags": delete_old_tags,
                        "tag_name_pattern": tag_name_pattern,
                        "delete_unused_namespaces": delete_unused_namespaces,
                        "target_namespace_id": target_namespace_id
                    }
                }
            },
            "statusCode": 200,
        }
        
    except Exception as e:
        return {
            "body": {
                "error": f"Erreur générale du script: {str(e)}",
                "summary": {
                    "total_images_analyzed": 0,
                    "total_tags_found": 0,
                    "successfully_deleted": 0,
                    "errors": 1,
                    "criteria_used": {
                        "delete_old_tags": delete_old_tags if 'delete_old_tags' in locals() else False,
                        "tag_name_pattern": tag_name_pattern if 'tag_name_pattern' in locals() else None,
                        "delete_unused_namespaces": delete_unused_namespaces if 'delete_unused_namespaces' in locals() else False,
                        "target_namespace_id": target_namespace_id if 'target_namespace_id' in locals() else None
                    }
                }
            },
            "statusCode": 500,
        }