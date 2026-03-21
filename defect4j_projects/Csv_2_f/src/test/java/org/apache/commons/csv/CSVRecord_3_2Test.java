package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_3_2Test {

    @Test
    @Timeout(8000)
    void testGet_withMappingAndExistingName_returnsValue() {
        String[] values = new String[] { "value1", "value2" };
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("key1", 0);
        mapping.put("key2", 1);
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);

        String result = record.get("key1");
        assertEquals("value1", result);

        result = record.get("key2");
        assertEquals("value2", result);
    }

    @Test
    @Timeout(8000)
    void testGet_withMappingAndNonExistingName_returnsNull() {
        String[] values = new String[] { "value1", "value2" };
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("key1", 0);
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);

        String result = record.get("nonExistingKey");
        assertNull(result);
    }

    @Test
    @Timeout(8000)
    void testGet_withNullMapping_throwsIllegalStateException() {
        String[] values = new String[] { "value1", "value2" };
        CSVRecord record = new CSVRecord(values, null, null, 1L);

        IllegalStateException exception = assertThrows(IllegalStateException.class, () -> {
            record.get("key1");
        });
        assertEquals("No header mapping was specified, the record values can't be accessed by name", exception.getMessage());
    }

    @Test
    @Timeout(8000)
    void testGet_usingReflection_onPublicMethod() throws Exception {
        String[] values = new String[] { "val0", "val1" };
        Map<String, Integer> mapping = Collections.singletonMap("a", 1);
        CSVRecord record = new CSVRecord(values, mapping, null, 1L);

        Method getMethod = CSVRecord.class.getMethod("get", String.class);
        Object result = getMethod.invoke(record, "a");
        assertEquals("val1", result);

        result = getMethod.invoke(record, "b");
        assertNull(result);
    }
}