"""The farmer profile's two S3 clients against Garage (endpoint, keys and region from env).
Odoo: storage_backend_s3 adapter calls (boto3.resource, head_bucket, upload_fileobj with
ContentType/CacheControl, read). ODK import service: boto3.client put_object."""
import io, os, sys
import boto3
ep, region = os.environ["EP"], os.environ["REGION"]
kw = dict(aws_access_key_id=os.environ["KID"], aws_secret_access_key=os.environ["KSK"],
          endpoint_url=ep, region_name=region)
data = os.urandom(120_000)
ok = True
s3 = boto3.resource("s3", **kw)
s3.meta.client.head_bucket(Bucket="documents")
obj = s3.Bucket("documents").Object(key="odoo-test-%s.webp" % boto3.__version__)
obj.upload_fileobj(io.BytesIO(data), ExtraArgs={"ContentType": "image/webp",
                                                "CacheControl": "max-age=31536000, public"})
ok &= obj.get()["Body"].read() == data
c = boto3.client("s3", **kw)
c.put_object(Bucket="documents", Key="odk-test-%s.webp" % boto3.__version__, Body=data)
ok &= c.get_object(Bucket="documents", Key="odk-test-%s.webp" % boto3.__version__)["Body"].read() == data
print(("PASS" if ok else "FAIL") + f": boto3 {boto3.__version__} region {region}: head_bucket, upload_fileobj, put_object, read back")
sys.exit(0 if ok else 1)
