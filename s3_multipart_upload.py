import argparse
import boto3
import json
import multiprocessing

# Starts Multipart Upload
def start_upload(bucket, key):
    s3_client = boto3.client('s3')

    response = s3_client.create_multipart_upload(
        Bucket = bucket,
        Key = key
    )

    return response['UploadId']

# Add upload part
def add_part(proc_queue, body, bucket, key, part_number, upload_id):
    s3_client = boto3.client('s3')

    response = s3_client.upload_part(
        Body = body,
        Bucket = bucket,
        Key = key,
        PartNumber = part_number,
        UploadId = upload_id
    )

    print(f"Finished Part: {part_number}, ETag: {response['ETag']}")
    proc_queue.put({'PartNumber': part_number, 'ETag': response['ETag']})
    return

# End Multipart Upload
def end_upload(bucket, key, upload_id, finished_parts):
    s3_client = boto3.client('s3')

    response = s3_client.complete_multipart_upload(
        Bucket = bucket,
        Key = key,
        MultipartUpload={
            'Parts': finished_parts
        },
        UploadId = upload_id
    )

    return response

# Primary Logic Function
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-f', '--file', required = True, help = "File to be chunked and uploaded")
    ap.add_argument('-k', '--key', help = "Key for destination object")
    ap.add_argument('-b', '--bucket', required = True, help = "Destination bucket")
    ap.add_argument('-cs', '--chunk_size', required = True, type = int, choices = range(5,101), metavar = '[5-100]', help = "Chunk size in MB, must be > 5MiB")
    ap.add_argument('-p', '--processes', type = int, choices = range(1,256), metavar = '[1-256]', default = 10, help = "Number of upload processes to run simultaneously")
    args = vars(ap.parse_args()) # Returns Dictionary Attributes
    
    # If key is not given, then consider the file name
    if args['key'] in [None, '']:
        args['key'] = args['file']

    file = args['file']
    key = args['key']
    bucket = args['bucket']
    sim_proc = args['processes']
    upload_id = start_upload(bucket, key)
    print(f'Starting upload: {upload_id}')
    
    file_upload = open(file, 'rb')
    part_procs = []
    proc_queue = multiprocessing.Queue()
    queue_returns = []
    chunk_size = (args['chunk_size'] * 1024) * 1024
    part_num = 1
    chunk = file_upload.read(chunk_size)
    
    # Create each process which uploads file by chunk size 
    while len(chunk) > 0:
        proc = multiprocessing.Process(target=add_part, args=(proc_queue, chunk, bucket, key, part_num, upload_id))
        part_procs.append(proc)
        part_num += 1
        chunk = file_upload.read(chunk_size)

    # Convert number of partial processes into batches of simultaneous processes
    num_batches = (len(part_procs) + (sim_proc - 1)) // sim_proc
    part_procs = [part_procs[i * sim_proc:(i +1) * sim_proc] for i in range(num_batches)]

    for i in range(len(part_procs)):
        for p in part_procs[i]:
            p.start() # Starting all the processes

        for p in part_procs[i]:
            p.join() # Waiting until all the processes complete

        for p in part_procs[i]:
            queue_returns.append(proc_queue.get())
    
    queue_returns = sorted(queue_returns, key = lambda i: i['PartNumber'])
    response = end_upload(bucket, key, upload_id, queue_returns)
    print(json.dumps(response, sort_keys=True, indent=4))

if __name__ == '__main__':
    main()