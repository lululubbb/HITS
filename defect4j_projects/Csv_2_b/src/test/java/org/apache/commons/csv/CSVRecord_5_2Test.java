package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Method;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_5_2Test {

    private Map<String, Integer> mappingMock;
    private CSVRecord csvRecordWithMapping;
    private CSVRecord csvRecordWithoutMapping;

    @BeforeEach
    public void setUp() {
        mappingMock = mock(Map.class);
        csvRecordWithMapping = new CSVRecord(
                new String[] { "val1", "val2" },
                mappingMock,
                "comment",
                1L);
        csvRecordWithoutMapping = new CSVRecord(
                new String[] { "val1", "val2" },
                null,
                "comment",
                1L);
    }

    @Test
    @Timeout(8000)
    public void testIsMapped_mappingNotNullAndContainsKeyTrue() {
        when(mappingMock.containsKey("key")).thenReturn(true);
        assertTrue(csvRecordWithMapping.isMapped("key"));
        verify(mappingMock).containsKey("key");
    }

    @Test
    @Timeout(8000)
    public void testIsMapped_mappingNotNullAndContainsKeyFalse() {
        when(mappingMock.containsKey("key")).thenReturn(false);
        assertFalse(csvRecordWithMapping.isMapped("key"));
        verify(mappingMock).containsKey("key");
    }

    @Test
    @Timeout(8000)
    public void testIsMapped_mappingNull() {
        assertFalse(csvRecordWithoutMapping.isMapped("key"));
    }

    @Test
    @Timeout(8000)
    public void testIsMapped_reflectionInvocation() throws Exception {
        Method method = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        method.setAccessible(true);

        when(mappingMock.containsKey("key")).thenReturn(true);
        boolean result = (boolean) method.invoke(csvRecordWithMapping, "key");
        assertTrue(result);

        result = (boolean) method.invoke(csvRecordWithoutMapping, "key");
        assertFalse(result);
    }
}