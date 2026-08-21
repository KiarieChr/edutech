class CommunicationProvider:
    def send_message(self, recipient, message, **kwargs):
        raise NotImplementedError
    
    def send_bulk(self, recipients, message, **kwargs):
        raise NotImplementedError
        
    def get_status(self, provider_message_id):
        raise NotImplementedError
        
    def parse_webhook(self, request):
        raise NotImplementedError
