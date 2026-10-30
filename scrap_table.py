import requests
import boto3
import uuid
import json
from datetime import datetime
from zoneinfo import ZoneInfo


def lambda_handler(event, context):

    anio = datetime.now(
        ZoneInfo("America/Lima")
    ).year

    url = f"https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb/{anio}"

    response = requests.get(url, timeout=20)

    if response.status_code != 200:
        return {
            "statusCode": response.status_code,
            "body": "Error al obtener datos del IGP"
        }

    datos = response.json()
    
    datos = sorted(
        datos,
        key=lambda s: int(s.get("numero_reporte") or 0),
        reverse=True
    )

    datos = datos[:10]

    if not isinstance(datos, list):
        return {
            "statusCode": 500,
            "body": "Formato de datos incorrecto"
        }

    if not datos:
        return {
            "statusCode": 404,
            "body": "No se encontraron sismos"
        }
        
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table("TablaSismosIGP")

    rows = []

    for sismo in datos:

        codigo = str(sismo.get("codigo") or "")

        if not codigo:
            continue

        fecha = str(sismo.get("fecha_local") or "")[:10]
        hora = str(sismo.get("hora_local") or "")[11:19]

        fecha_hora = f"{fecha} {hora}".strip()

        magnitud = sismo.get("magnitud")
        try:
            magnitud_num = float(magnitud)
        except (TypeError, ValueError):
            magnitud_num = None

        if magnitud_num is None:
            semaforo = "No disponible"
        elif magnitud_num < 4.5:
            semaforo = "Verde"
        elif magnitud_num < 6.0:
            semaforo = "Amarillo"
        else:
            semaforo = "Rojo"

        row = {
            "id": str(uuid.uuid4()),
            "Cod reporte": codigo,
            "Referencia": str(sismo.get("referencia") or ""),
            "Semáforo": semaforo,
            "Magnitud": str(magnitud or ""),
            "Fecha y hora de origen local": fecha_hora,
            "Latitud": str(sismo.get("latitud") or ""),
            "Longitud": str(sismo.get("longitud") or ""),
            "Profundidad": str(sismo.get("profundidad") or ""),
            "Intensidad máxima (MM)": str(sismo.get("intensidad") or "")
        }

        rows.append(row)

    if not rows:
        return {
            "statusCode": 404,
            "body": "No se encontraron registros válidos"
        }
        
    scan_args = {}

    with table.batch_writer() as batch:

        while True:
            resultado = table.scan(**scan_args)

            for item in resultado["Items"]:
                batch.delete_item(Key={"id": item["id"]})

            if "LastEvaluatedKey" not in resultado:
                break

            scan_args["ExclusiveStartKey"] = resultado["LastEvaluatedKey"]

    with table.batch_writer() as batch:
        for row in rows:
            batch.put_item(Item=row)
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json; charset=utf-8"
        },
        "body": json.dumps(
            {
                "total": len(rows),
                "sismos": rows
            },
            ensure_ascii=False
        )
    } 
