package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Constructor;
import java.util.Map;

import org.junit.jupiter.api.Test;

public class CSVRecord_5_4Test {

    @Test
    @Timeout(8000)
    public void testIsMapped_MappingIsNull() throws Exception {
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = null;
        String comment = "comment";
        long recordNumber = 1L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertFalse(record.isMapped("anyKey"));
    }

    @Test
    @Timeout(8000)
    public void testIsMapped_MappingDoesNotContainKey() throws Exception {
        Map<String, Integer> mapping = mock(Map.class);
        when(mapping.containsKey("missingKey")).thenReturn(false);

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(new String[] {"v1", "v2"}, mapping, "comment", 2L);

        assertFalse(record.isMapped("missingKey"));
        verify(mapping).containsKey("missingKey");
    }

    @Test
    @Timeout(8000)
    public void testIsMapped_MappingContainsKey() throws Exception {
        Map<String, Integer> mapping = mock(Map.class);
        when(mapping.containsKey("existingKey")).thenReturn(true);

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(new String[] {"v1", "v2"}, mapping, "comment", 3L);

        assertTrue(record.isMapped("existingKey"));
        verify(mapping).containsKey("existingKey");
    }
}